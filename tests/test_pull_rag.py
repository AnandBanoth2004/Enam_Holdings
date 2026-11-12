from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import fitz
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finn_api.db.base import Base
from finn_api.db.models import Company, Document, DocumentChunk
from finn_api.pull.answering import (
    AnswerGenerationError,
    generate_grounded_answer,
)
from finn_api.pull.chunking import chunk_document
from finn_api.pull.documents import DocumentDownloadError, PrimaryDocumentDownloader
from finn_api.pull.ingestion import ingest_primary_document
from finn_api.pull.pdf_processing import DocumentProcessingError, extract_pdf
from finn_api.pull.retrieval import DocumentRetriever, EvidenceChunk


def _pdf_bytes(pages: list[str]) -> bytes:
    pdf = fitz.open()
    for text in pages:
        page = pdf.new_page()
        page.insert_textbox((48, 48, 540, 760), text, fontsize=11)
    content = pdf.tobytes()
    pdf.close()
    return content


def test_downloader_follows_approved_https_redirects() -> None:
    pdf = b"%PDF-1.7\nprimary source"

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "issuer.example":
            return httpx.Response(
                301,
                headers={"location": "https://cdn.issuer.example/report.pdf"},
                request=request,
            )
        return httpx.Response(
            200,
            content=pdf,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    downloader = PrimaryDocumentDownloader(client=client)
    try:
        result = downloader.download(
            "https://issuer.example/report.pdf",
            trusted_hosts=("issuer.example",),
        )
    finally:
        client.close()

    assert result.content == pdf


def test_downloader_rejects_unapproved_redirect_before_requesting_target() -> None:
    requested_hosts: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    downloader = PrimaryDocumentDownloader(client=client)
    try:
        with pytest.raises(DocumentDownloadError) as error:
            downloader.download(
                "https://issuer.example/report.pdf",
                trusted_hosts=("issuer.example",),
            )
    finally:
        client.close()

    assert error.value.code == "untrusted_document_redirect"
    assert requested_hosts == ["issuer.example"]


def _company_and_document(
    session: Session,
    *,
    ticker: str,
    company_name: str,
    text: str,
    document_type: str = "annual_report",
    period_label: str = "FY2025-26",
    synthetic: bool = False,
) -> tuple[Company, Document, DocumentChunk]:
    company = Company(
        legal_name=company_name,
        display_name=company_name,
        synthetic=synthetic,
    )
    session.add(company)
    session.flush()
    document = Document(
        company_id=company.id,
        document_type=document_type,
        title=f"{company_name} Annual Report FY2025-26",
        source_url=f"https://issuer.example/{ticker.lower()}-annual-report.pdf",
        source_name="issuer.example",
        period_start=date(2025, 4, 1),
        period_end=date(2026, 3, 31),
        period_label=period_label,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        ingestion_status="extracted",
        synthetic=synthetic,
        is_primary_source=True,
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(document)
    session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        page_start=2,
        page_end=2,
        section="Financial highlights",
        text=text,
        token_count=len(text.split()),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        synthetic=synthetic,
    )
    session.add(chunk)
    session.flush()
    return company, document, chunk


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_pdf_extraction_preserves_pages_tables_and_reporting_period() -> None:
    pdf = _pdf_bytes(
        [
            "Example Industries Limited\nAnnual Report FY2025-26\n"
            "BUSINESS OVERVIEW\nThe company operates in India.",
            "Consolidated Financial Statements\n"
            "Consolidated Statement of Profit and Loss\n"
            "FINANCIAL RESULTS\nRevenue | FY2025-26\n"
            "Net sales | 1200",
        ]
    )

    extracted = extract_pdf(
        pdf,
        ticker="EXAMPLE",
        company_names=("Example Industries Limited",),
        document_type="annual_report",
        title="Example Industries Annual Report FY2025-26",
    )

    assert extracted.period_label == "FY2025-26"
    assert extracted.period_start == date(2025, 4, 1)
    assert extracted.period_end == date(2026, 3, 31)
    assert [page.page_number for page in extracted.pages] == [1, 2]
    assert "BUSINESS OVERVIEW" in extracted.pages[0].text
    assert "Net sales | 1200" in extracted.pages[1].text
    assert "FINANCIAL_STATEMENT_LAYOUT:" in extracted.pages[1].text


def test_pdf_extraction_rejects_wrong_company_type_and_period() -> None:
    pdf = _pdf_bytes(
        [
            "Other Holdings Limited\nAnnual Report FY2025-26\n"
            "Business overview and audited statements.",
        ]
    )
    with pytest.raises(DocumentProcessingError, match="expected issuer"):
        extract_pdf(
            pdf,
            ticker="EXAMPLE",
            company_names=("Example Industries Limited",),
            document_type="annual_report",
            title="Example Industries Annual Report FY2025-26",
        )

    pdf = _pdf_bytes(
        [
            "Example Industries Limited\nQuarterly Financial Results Q2 FY2026\n"
            "Revenue results.",
        ]
    )
    with pytest.raises(DocumentProcessingError, match="looks like quarterly_result"):
        extract_pdf(
            pdf,
            ticker="EXAMPLE",
            company_names=("Example Industries Limited",),
            document_type="annual_report",
            title="Example Industries Annual Report",
        )
    with pytest.raises(DocumentProcessingError, match="requested reporting period"):
        extract_pdf(
            pdf,
            ticker="EXAMPLE",
            company_names=("Example Industries Limited",),
            document_type="quarterly_result",
            title="Example Industries Q2 Results",
            expected_period="Q1 FY2026",
        )


def test_ocr_is_only_invoked_for_pages_without_extractable_text(monkeypatch) -> None:
    calls: list[int] = []

    def fake_ocr(_: bytes, page_number: int) -> str:
        calls.append(page_number)
        return "Example Industries Limited Annual Report FY2025-26"

    monkeypatch.setattr("finn_api.pull.pdf_processing._ocr_page", fake_ocr)
    scanned_pdf = _pdf_bytes([""])
    extracted = extract_pdf(
        scanned_pdf,
        ticker="EXAMPLE",
        company_names=("Example Industries Limited",),
        document_type="annual_report",
        title="Example Industries Annual Report FY2025-26",
    )
    assert calls == [1]
    assert extracted.extraction_method == "pdf_text+ocr"

    calls.clear()
    digital_pdf = _pdf_bytes(
        ["Example Industries Limited Annual Report FY2025-26\nAudited statements."]
    )
    extract_pdf(
        digital_pdf,
        ticker="EXAMPLE",
        company_names=("Example Industries Limited",),
        document_type="annual_report",
        title="Example Industries Annual Report FY2025-26",
    )
    assert calls == []


def test_chunking_keeps_page_and_heading_provenance() -> None:
    extracted = extract_pdf(
        _pdf_bytes(
            [
                "Example Industries Limited Annual Report FY2025-26\n"
                "OPERATIONS\n" + ("Revenue increased across divisions. " * 35),
                "CASH FLOW\n" + ("Cash generated from operations. " * 35),
            ]
        ),
        ticker="EXAMPLE",
        company_names=("Example Industries Limited",),
        document_type="annual_report",
        title="Example Industries Annual Report FY2025-26",
    )

    chunks = chunk_document(extracted, max_tokens=50)
    assert len(chunks) > 2
    assert all(chunk.page_start == chunk.page_end for chunk in chunks)
    assert {chunk.page_start for chunk in chunks} == {1, 2}
    assert all(chunk.token_count <= 50 for chunk in chunks)
    assert any(chunk.section == "OPERATIONS" for chunk in chunks)


def test_retrieval_filters_by_company_type_period_and_primary_source(db_engine) -> None:
    with Session(db_engine) as session:
        company_a, _, _ = _company_and_document(
            session,
            ticker="EXAMPLE",
            company_name="Example Industries Limited",
            text="Revenue grew 12 percent. EBITDA margin improved.",
        )
        _company_and_document(
            session,
            ticker="OTHER",
            company_name="Other Holdings Limited",
            text="Revenue increased 99 percent.",
        )
        secondary = Document(
            company_id=company_a.id,
            document_type="annual_report",
            title="Secondary research report",
            source_url="https://issuer.example/secondary.pdf",
            source_name="issuer.example",
            content_hash="secondary-hash",
            ingestion_status="extracted",
            is_primary_source=False,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(secondary)
        session.flush()
        session.add(
            DocumentChunk(
                document_id=secondary.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                text="Revenue commentary from a secondary report.",
                token_count=6,
                content_hash="secondary-chunk",
            )
        )
        session.commit()

        results = DocumentRetriever().retrieve(
            session,
            company_id=company_a.id,
            ticker="EXAMPLE",
            query="Revenue EBITDA",
            document_types=("annual_report",),
            period_start=date(2025, 4, 1),
            period_end=date(2026, 3, 31),
        )

    assert len(results) == 1
    assert results[0].ticker == "EXAMPLE"
    assert results[0].page_number == 2
    assert "Revenue grew" in results[0].text


def test_retrieval_cache_keys_include_query_and_filters(db_engine) -> None:
    with Session(db_engine) as session:
        company, _, _ = _company_and_document(
            session,
            ticker="EXAMPLE",
            company_name="Example Industries Limited",
            text="Revenue grew and EBITDA margin improved.",
        )
        session.commit()
        retriever = DocumentRetriever()
        first = retriever.retrieve(
            session,
            company_id=company.id,
            ticker="EXAMPLE",
            query="revenue",
        )
        same = retriever.retrieve(
            session,
            company_id=company.id,
            ticker="EXAMPLE",
            query="revenue",
        )
        different = retriever.retrieve(
            session,
            company_id=company.id,
            ticker="EXAMPLE",
            query="dividend",
        )

    assert first == same
    assert first
    assert different == ()


def test_grounded_answer_cites_verbatim_source_with_document_page_and_url() -> None:
    evidence = (
        EvidenceChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            ticker="EXAMPLE",
            document_type="quarterly_result",
            document_name="Example Industries Q2 Results",
            period_label="Q2 FY2026",
            page_number=4,
            page_end=4,
            source_url="https://issuer.example/q2-results.pdf",
            text="Revenue from operations was Rs 1,200 crore for the quarter.",
            score=0.9,
            synthetic=False,
        ),
    )
    answer = generate_grounded_answer(
        ticker="EXAMPLE",
        question="What was quarterly revenue?",
        evidence=evidence,
    )

    assert answer.status == "evidence_only"
    claim = answer.claims[0]
    assert claim.text in evidence[0].text
    assert claim.citations[0].document_name == "Example Industries Q2 Results"
    assert claim.citations[0].reporting_period == "Q2 FY2026"
    assert claim.citations[0].page_number == 4
    assert claim.citations[0].source_url == evidence[0].source_url


def test_missing_evidence_abstains_without_making_a_claim() -> None:
    answer = generate_grounded_answer(
        ticker="EXAMPLE",
        question="What is the company's FY2026 revenue?",
        evidence=(),
    )
    assert answer.status == "insufficient_evidence"
    assert answer.claims == []
    assert answer.source_count == 0


def test_invalid_or_nonverbatim_model_citations_are_rejected() -> None:
    class FakeModel:
        model = "test-json-model"

        def __init__(self, response: str) -> None:
            self.response = response

        def answer(self, *, question: str, evidence: list[dict[str, str]]) -> str:
            return self.response

    evidence = (
        EvidenceChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            ticker="EXAMPLE",
            document_type="annual_report",
            document_name="Example Annual Report",
            period_label="FY2025-26",
            page_number=1,
            page_end=1,
            source_url="https://issuer.example/annual-report.pdf",
            text="Revenue rose in the reported financial year.",
            score=0.8,
            synthetic=False,
        ),
    )
    unknown_id = uuid4()
    fake = FakeModel(
        json.dumps(
            {
                "claims": [
                    {
                        "text": "Revenue grew by 80%.",
                        "claim_type": "reported_fact",
                        "evidence_quotes": [
                            {"chunk_id": str(unknown_id), "quote": "Revenue rose"}
                        ],
                    }
                ],
                "limitations": [],
            }
        )
    )
    with pytest.raises(AnswerGenerationError, match="not retrieved"):
        generate_grounded_answer(
            ticker="EXAMPLE",
            question="Revenue?",
            evidence=evidence,
            research_model=fake,
        )

    fake.response = json.dumps(
        {
            "claims": [
                {
                    "text": "Revenue grew by 80%.",
                    "claim_type": "reported_fact",
                    "evidence_quotes": [
                        {
                            "chunk_id": str(evidence[0].chunk_id),
                            "quote": "Revenue grew by 80%.",
                        }
                    ],
                }
            ],
            "limitations": [],
        }
    )
    with pytest.raises(AnswerGenerationError, match="not present verbatim"):
        generate_grounded_answer(
            ticker="EXAMPLE",
            question="Revenue?",
            evidence=evidence,
            research_model=fake,
        )


def test_document_ingestion_deduplicates_content_across_source_urls(
    db_engine,
    tmp_path: Path,
) -> None:
    pdf = _pdf_bytes(
        ["Example Industries Limited Annual Report FY2025-26\n"
         "Business overview and audited statements."]
    )
    digest = hashlib.sha256(pdf).hexdigest()

    with Session(db_engine) as session:
        company = Company(
            legal_name="Example Industries Limited",
            display_name="Example Industries Limited",
        )
        session.add(company)
        session.flush()
        original = Document(
            company_id=company.id,
            document_type="annual_report",
            title="Original annual report",
            source_url="https://issuer.example/original.pdf",
            source_name="issuer.example",
            content_hash=digest,
            ingestion_status="extracted",
            is_primary_source=True,
            fetched_at=datetime.now(timezone.utc),
        )
        duplicate = Document(
            company_id=company.id,
            document_type="annual_report",
            title="Duplicate annual report",
            source_url="https://issuer.example/duplicate.pdf",
            source_name="issuer.example",
            content_hash="discovery-url-hash",
            ingestion_status="discovered",
            is_primary_source=True,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add_all((original, duplicate))
        session.commit()

        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=pdf,
                    headers={"content-type": "application/pdf"},
                    request=request,
                )
            )
        )
        downloader = PrimaryDocumentDownloader(client=client)
        outcome = ingest_primary_document(
            session,
            document=duplicate,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=None,
        )
        client.close()

        saved = session.scalar(
            select(Document).where(Document.id == duplicate.id)
        )
        chunk_count = session.query(DocumentChunk).count()

    assert outcome.status == "duplicate"
    assert outcome.duplicate_of == original.id
    assert saved is not None
    assert saved.ingestion_status == "duplicate"
    assert chunk_count == 0


def test_ingestion_persists_pages_and_is_idempotent_for_unchanged_content(
    db_engine,
    tmp_path: Path,
) -> None:
    pdf = _pdf_bytes(
        [
            "Example Industries Limited Annual Report FY2025-26\n"
            "OPERATIONS\nRevenue from domestic operations improved.",
        ]
    )
    with Session(db_engine) as session:
        company = Company(
            legal_name="Example Industries Limited",
            display_name="Example Industries Limited",
        )
        session.add(company)
        session.flush()
        document = Document(
            company_id=company.id,
            document_type="annual_report",
            title="Example Industries Annual Report FY2025-26",
            source_url="https://issuer.example/annual-report.pdf",
            source_name="issuer.example",
            content_hash="discovery-url-hash",
            ingestion_status="discovered",
            is_primary_source=True,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(document)
        session.commit()

        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=pdf,
                    headers={"content-type": "application/pdf"},
                    request=request,
                )
            )
        )
        downloader = PrimaryDocumentDownloader(client=client)
        first = ingest_primary_document(
            session,
            document=document,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=None,
        )
        second = ingest_primary_document(
            session,
            document=document,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=None,
        )
        client.close()

        chunks = session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        ).all()

    assert first.document_id == document.id
    assert first.status == "extracted"
    assert first.page_count == 1
    assert first.chunk_count == 2
    assert second.document_id == first.document_id
    assert second.chunk_count == 2
    assert document.storage_path is not None
    assert Path(document.storage_path).is_file()
    assert [chunk.page_start for chunk in chunks] == [1, 1]
    assert [chunk.section for chunk in chunks] == [None, "OPERATIONS"]
    assert all(chunk.embedding is None for chunk in chunks)


def test_ingestion_batches_unique_chunk_embeddings_and_reuses_duplicate_text(
    db_engine,
    tmp_path: Path,
) -> None:
    page_texts = [
        "Example Industries Limited Annual Report FY2025-26\n"
        f"The report discusses unique operating segment number {index}."
        for index in range(65)
    ]
    page_texts.append(page_texts[0])
    pdf = _pdf_bytes(page_texts)

    class CountingEmbeddingProvider:
        embedding_model = "test-embedding-model"

        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.batch_sizes.append(len(texts))
            return [[1.0] for _ in texts]

    provider = CountingEmbeddingProvider()
    with Session(db_engine) as session:
        company = Company(
            legal_name="Example Industries Limited",
            display_name="Example Industries Limited",
        )
        session.add(company)
        session.flush()
        document = Document(
            company_id=company.id,
            document_type="annual_report",
            title="Example Industries Annual Report FY2025-26",
            source_url="https://issuer.example/annual-report.pdf",
            source_name="issuer.example",
            content_hash="discovery-url-hash",
            ingestion_status="discovered",
            is_primary_source=True,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(document)
        session.commit()

        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=pdf,
                    headers={"content-type": "application/pdf"},
                    request=request,
                )
            )
        )
        downloader = PrimaryDocumentDownloader(client=client)
        result = ingest_primary_document(
            session,
            document=document,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=provider,
            embedding_dimensions=1,
        )
        client.close()

    assert result.page_count == 66
    assert result.chunk_count == 66
    assert result.embedded_chunk_count == 66
    assert provider.batch_sizes == [64, 1]


def test_changed_document_content_is_retained_as_a_new_version(
    db_engine,
    tmp_path: Path,
) -> None:
    first_pdf = _pdf_bytes(
        [
            "Example Industries Limited Annual Report FY2025-26\n"
            "The prior report discussed legacy operations.",
        ]
    )
    updated_pdf = _pdf_bytes(
        [
            "Example Industries Limited Annual Report FY2025-26\n"
            "The updated report discussed current operations.",
        ]
    )
    content = {"pdf": first_pdf}
    with Session(db_engine) as session:
        company = Company(
            legal_name="Example Industries Limited",
            display_name="Example Industries Limited",
        )
        session.add(company)
        session.flush()
        document = Document(
            company_id=company.id,
            document_type="annual_report",
            title="Example Industries Annual Report FY2025-26",
            source_url="https://issuer.example/annual-report.pdf",
            source_name="issuer.example",
            content_hash="discovery-url-hash",
            ingestion_status="discovered",
            is_primary_source=True,
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(document)
        session.commit()

        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=content["pdf"],
                    headers={"content-type": "application/pdf"},
                    request=request,
                )
            )
        )
        downloader = PrimaryDocumentDownloader(client=client)
        original = ingest_primary_document(
            session,
            document=document,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=None,
        )
        content["pdf"] = updated_pdf
        current = ingest_primary_document(
            session,
            document=document,
            ticker="EXAMPLE",
            downloader=downloader,
            storage_directory=tmp_path,
            embedding_provider=None,
        )
        client.close()

        versions = session.scalars(
            select(Document)
            .where(Document.company_id == company.id)
            .order_by(Document.created_at)
        ).all()
        chunks = session.scalars(
            select(DocumentChunk).join(Document).where(Document.company_id == company.id)
        ).all()
        current_results = DocumentRetriever().retrieve(
            session,
            company_id=company.id,
            ticker="EXAMPLE",
            query="current operations",
        )

    assert current.document_id != original.document_id
    assert len(versions) == 2
    assert {version.ingestion_status for version in versions} == {
        "superseded",
        "extracted",
    }
    assert len(chunks) == 2
    assert len(current_results) == 1
    assert "current operations" in current_results[0].text
