from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finn_api.db.models import Company, Document, DocumentChunk
from finn_api.pull.chunking import TextChunk, chunk_document
from finn_api.pull.documents import (
    DocumentDownloadError,
    PrimaryDocumentDownloader,
)
from finn_api.pull.pdf_processing import DocumentProcessingError, extract_pdf
from finn_api.pull.providers import EmbeddingProvider

logger = logging.getLogger(__name__)
_EMBEDDING_BATCH_SIZE = 64


@dataclass(frozen=True)
class IngestionOutcome:
    document_id: UUID
    status: str
    duplicate_of: UUID | None
    page_count: int
    chunk_count: int
    embedded_chunk_count: int
    embedding_model: str | None
    extraction_method: str | None
    period_label: str | None


def _storage_path(root: Path, company_id: UUID, content_hash: str) -> tuple[Path, Path]:
    directory = root / str(company_id)
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / f"{content_hash}.pdf"
    temporary_path = directory / f"{content_hash}.pdf.tmp"
    return final_path, temporary_path


def _save_document(
    session: Session,
    *,
    document: Document,
    company: Company,
    chunks: tuple[TextChunk, ...],
    content_hash: str,
    content_type: str,
    file_size_bytes: int,
    storage_path: Path,
    period_label: str | None,
    period_start: date | None,
    period_end: date | None,
    extraction_method: str,
    embedding_provider: EmbeddingProvider | None,
    embedding_dimensions: int,
) -> int:
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    document.content_hash = content_hash
    document.content_type = content_type
    document.file_size_bytes = file_size_bytes
    document.storage_path = str(storage_path)
    document.extracted_at = datetime.now(timezone.utc)
    document.period_label = period_label
    document.period_start = period_start
    document.period_end = period_end
    document.extraction_method = extraction_method
    document.is_primary_source = True
    document.ingestion_status = "extracted"
    document.fetched_at = datetime.now(timezone.utc)

    reusable: dict[str, list[float]] = {}
    hashes = [chunk.content_hash for chunk in chunks]
    if embedding_provider and hashes:
        rows = session.scalars(
            select(DocumentChunk).where(
                DocumentChunk.content_hash.in_(hashes),
                DocumentChunk.embedding_model == embedding_provider.embedding_model,
                DocumentChunk.embedding.is_not(None),
            )
        ).all()
        reusable = {
            chunk.content_hash: list(chunk.embedding)
            for chunk in rows
            if chunk.embedding is not None
        }

    pending_by_hash = {
        chunk.content_hash: chunk
        for chunk in chunks
        if chunk.content_hash not in reusable
    }
    pending = list(pending_by_hash.values())
    new_vectors: dict[str, list[float]] = {}
    if embedding_provider and pending:
        for start in range(0, len(pending), _EMBEDDING_BATCH_SIZE):
            batch = pending[start : start + _EMBEDDING_BATCH_SIZE]
            vectors = embedding_provider.embed([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise ValueError(
                    "Embedding provider returned the wrong number of vectors."
                )
            for chunk, vector in zip(batch, vectors, strict=True):
                if len(vector) != embedding_dimensions or any(
                    not math.isfinite(value) for value in vector
                ):
                    raise ValueError(
                        "Embedding provider returned a vector with an invalid dimension or value."
                    )
                new_vectors[chunk.content_hash] = vector

    embedded_count = 0
    for chunk in chunks:
        vector = reusable.get(chunk.content_hash) or new_vectors.get(chunk.content_hash)
        if vector is not None:
            embedded_count += 1
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section=chunk.section,
                text=chunk.text,
                token_count=chunk.token_count,
                embedding=vector,
                embedding_model=(
                    embedding_provider.embedding_model if vector is not None else None
                ),
                content_hash=chunk.content_hash,
                synthetic=document.synthetic,
            )
        )
    document.ingestion_status = (
        "embedded"
        if chunks and embedded_count == len(chunks)
        else "extracted"
    )
    session.flush()
    return embedded_count


def ingest_primary_document(
    session: Session,
    *,
    document: Document,
    ticker: str,
    downloader: PrimaryDocumentDownloader,
    storage_directory: Path,
    embedding_provider: EmbeddingProvider | None,
    trusted_document_hosts: tuple[str, ...] = (),
    embedding_dimensions: int = 1536,
    expected_period: str | None = None,
    max_chunk_tokens: int = 700,
) -> IngestionOutcome:
    if not document.is_primary_source or document.synthetic:
        raise DocumentProcessingError(
            "ineligible_research_document",
            "Pull ingestion accepts only verified, non-synthetic primary-source documents.",
        )
    company = session.get(Company, document.company_id)
    if company is None:
        raise LookupError("The document's company is not available.")
    if not document.source_name.strip():
        raise DocumentDownloadError(
            "missing_trusted_source_host",
            "The discovered document has no verified issuer host.",
        )

    try:
        downloaded = downloader.download(
            document.source_url,
            trusted_hosts=tuple(
                dict.fromkeys((document.source_name, *trusted_document_hosts))
            ),
        )
        extracted = extract_pdf(
            downloaded.content,
            ticker=ticker,
            company_names=(company.legal_name, company.display_name),
            document_type=document.document_type,
            title=document.title,
            expected_period=expected_period or document.period_label,
        )
    except (DocumentDownloadError, DocumentProcessingError) as error:
        document.ingestion_status = "rejected"
        session.commit()
        logger.warning(
            "Primary document rejected document_id=%s error_code=%s",
            document.id,
            error.code,
        )
        raise

    chunks = chunk_document(extracted, max_tokens=max_chunk_tokens)
    final_path, temporary_path = _storage_path(
        storage_directory,
        company.id,
        downloaded.content_hash,
    )

    duplicate = session.scalar(
        select(Document)
        .where(
            Document.company_id == company.id,
            Document.content_hash == downloaded.content_hash,
            Document.ingestion_status.in_(("extracted", "embedded", "downloaded")),
            Document.id != document.id,
        )
        .limit(1)
    )
    if (
        document.content_hash == downloaded.content_hash
        and document.ingestion_status in ("extracted", "embedded")
    ):
        existing_chunks = session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).all()
        document.fetched_at = datetime.now(timezone.utc)
        session.commit()
        return IngestionOutcome(
            document_id=document.id,
            status=document.ingestion_status,
            duplicate_of=None,
            page_count=len(extracted.pages),
            chunk_count=len(existing_chunks),
            embedded_chunk_count=sum(
                chunk.embedding is not None for chunk in existing_chunks
            ),
            embedding_model=(
                embedding_provider.embedding_model if embedding_provider else None
            ),
            extraction_method=document.extraction_method,
            period_label=document.period_label,
        )
    if duplicate is not None:
        document.content_hash = downloaded.content_hash
        document.file_size_bytes = len(downloaded.content)
        document.content_type = downloaded.content_type
        document.ingestion_status = "duplicate"
        document.extracted_at = datetime.now(timezone.utc)
        session.commit()
        return IngestionOutcome(
            document_id=document.id,
            status="duplicate",
            duplicate_of=duplicate.id,
            page_count=len(extracted.pages),
            chunk_count=0,
            embedded_chunk_count=0,
            embedding_model=(
                embedding_provider.embedding_model if embedding_provider else None
            ),
            extraction_method=extracted.extraction_method,
            period_label=extracted.period_label,
        )

    if document.ingestion_status in ("extracted", "embedded"):
        previous_version = document
        document = Document(
            company_id=previous_version.company_id,
            document_type=previous_version.document_type,
            title=previous_version.title,
            source_url=previous_version.source_url,
            source_name=previous_version.source_name,
            period_start=previous_version.period_start,
            period_end=previous_version.period_end,
            period_label=previous_version.period_label,
            published_at=previous_version.published_at,
            reporting_basis=previous_version.reporting_basis,
            language=previous_version.language,
            content_type=previous_version.content_type,
            file_size_bytes=previous_version.file_size_bytes,
            storage_path=previous_version.storage_path,
            extracted_at=previous_version.extracted_at,
            extraction_method=previous_version.extraction_method,
            content_hash=downloaded.content_hash,
            ingestion_status="discovered",
            data_source_id=previous_version.data_source_id,
            synthetic=previous_version.synthetic,
            is_primary_source=previous_version.is_primary_source,
            fetched_at=datetime.now(timezone.utc),
        )
        previous_version.ingestion_status = "superseded"
        session.add(document)
        session.flush()

    temporary_path.write_bytes(downloaded.content)
    temporary_path.replace(final_path)
    try:
        embedded_count = _save_document(
            session,
            document=document,
            company=company,
            chunks=chunks,
            content_hash=downloaded.content_hash,
            content_type=downloaded.content_type,
            file_size_bytes=len(downloaded.content),
            storage_path=final_path,
            period_label=extracted.period_label,
            period_start=extracted.period_start,
            period_end=extracted.period_end,
            extraction_method=extracted.extraction_method,
            embedding_provider=embedding_provider,
            embedding_dimensions=embedding_dimensions,
        )
        session.commit()
    except Exception:
        session.rollback()
        final_path.unlink(missing_ok=True)
        raise

    return IngestionOutcome(
        document_id=document.id,
        status=document.ingestion_status,
        duplicate_of=None,
        page_count=len(extracted.pages),
        chunk_count=len(chunks),
        embedded_chunk_count=embedded_count,
        embedding_model=(
            embedding_provider.embedding_model if embedding_provider else None
        ),
        extraction_method=extracted.extraction_method,
        period_label=extracted.period_label,
    )
