import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
sys.path.insert(0, str(backend_dir))

from finn_api.config import get_settings  # noqa: E402
from finn_api.data_pipeline.company_documents import (  # noqa: E402
    CompanyDocumentDiscoveryService,
    persist_company_documents,
)
from finn_api.data_pipeline.validation import normalize_nse_ticker  # noqa: E402
from finn_api.db.engine import SessionLocal, engine  # noqa: E402
from finn_api.db.models import Company, CompanyAlias, Document  # noqa: E402
from finn_api.pull.answering import generate_grounded_answer  # noqa: E402
from finn_api.pull.companies import resolve_company_and_website  # noqa: E402
from finn_api.pull.documents import PrimaryDocumentDownloader  # noqa: E402
from finn_api.pull.ingestion import ingest_primary_document  # noqa: E402
from finn_api.pull.pdf_processing import ALLOWED_DOCUMENT_TYPES  # noqa: E402
from finn_api.pull.providers import OpenAICompatibleProvider  # noqa: E402
from finn_api.pull.retrieval import DocumentRetriever  # noqa: E402


def _approved_source_host(
    source_url: str,
    *,
    issuer_website: str | None,
    allowed_hosts: tuple[str, ...],
) -> str | None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    issuer_host = urlparse(issuer_website or "").hostname
    trusted_hosts = {host.casefold().strip(".") for host in allowed_hosts if host.strip(".")}
    if issuer_host:
        trusted_hosts.add(issuer_host.casefold().strip("."))
    hostname = parsed.hostname.casefold().rstrip(".")
    if any(
        hostname == trusted or hostname.endswith(f".{trusted}")
        for trusted in trusted_hosts
    ):
        return hostname
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover, ingest, retrieve, and cite a company primary document."
    )
    parser.add_argument("--ticker", required=True, help="Supported NSE symbol.")
    parser.add_argument("--question", required=True, help="Research question.")
    parser.add_argument(
        "--document-type",
        choices=ALLOWED_DOCUMENT_TYPES,
        default="annual_report",
    )
    parser.add_argument("--title-contains", default="")
    parser.add_argument("--issuer-website")
    parser.add_argument(
        "--source-url",
        help="Explicit primary PDF URL from the issuer site or an authorized CDN.",
    )
    parser.add_argument("--document-title", help="Title for an explicitly supplied PDF URL.")
    parser.add_argument(
        "--allowed-document-host",
        action="append",
        default=[],
        help="Company-authorized CDN hostname; may be supplied more than once.",
    )
    args = parser.parse_args()
    ticker = normalize_nse_ticker(args.ticker)
    settings = get_settings()

    with SessionLocal() as session:
        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == "NSE",
                CompanyAlias.normalized_symbol == ticker,
            )
        )
        if alias is None:
            company, issuer_website = resolve_company_and_website(session, ticker)
        else:
            company = session.get(Company, alias.company_id)
            if company is None:
                raise LookupError(f"Company mapping for {ticker} is broken.")
            if args.issuer_website:
                issuer_website = args.issuer_website
            else:
                _, issuer_website = resolve_company_and_website(session, ticker)

        discovery = CompanyDocumentDiscoveryService()
        try:
            discovered = discovery.discover(
                ticker,
                issuer_website=args.issuer_website or issuer_website,
                allowed_document_hosts=tuple(
                    [*settings.configured_document_hosts, *args.allowed_document_host]
                ),
            )
        finally:
            discovery.close()
        persist_company_documents(session, discovered, company_id=company.id)
        if args.source_url:
            trusted_hosts = tuple(
                [*settings.configured_document_hosts, *args.allowed_document_host]
            )
            source_host = _approved_source_host(
                args.source_url,
                issuer_website=args.issuer_website or issuer_website,
                allowed_hosts=trusted_hosts,
            )
            if source_host is None:
                parser.error(
                    "--source-url must be HTTPS and use the issuer host or an explicitly authorized document host."
                )
            document = session.scalar(
                select(Document).where(
                    Document.company_id == company.id,
                    Document.source_url == args.source_url,
                    Document.document_type == args.document_type,
                )
            )
            if document is None:
                document = Document(
                    company_id=company.id,
                    document_type=args.document_type,
                    title=args.document_title or Path(urlparse(args.source_url).path).name,
                    source_url=args.source_url,
                    source_name=source_host,
                    content_hash=hashlib.sha256(args.source_url.encode("utf-8")).hexdigest(),
                    ingestion_status="discovered",
                    is_primary_source=True,
                    fetched_at=datetime.now(timezone.utc),
                )
                session.add(document)
                session.flush()
            elif not document.is_primary_source or document.synthetic:
                parser.error("The selected document URL is already marked ineligible.")
            documents = [document]
        else:
            documents = [
                document
                for document in session.scalars(
                    select(Document).where(
                        Document.company_id == company.id,
                        Document.ingestion_status != "superseded",
                        Document.source_url.in_(
                            [item.source_url for item in discovered.documents] or [""]
                        ),
                    )
                ).all()
                if document.document_type == args.document_type
                and args.title_contains.casefold() in document.title.casefold()
            ]
        if not documents:
            available = [
                {
                    "type": item.document_type,
                    "title": item.title,
                    "source_url": item.source_url,
                }
                for item in discovered.documents
            ]
            raise LookupError(
                "No document matched the requested selection. Discovered documents: "
                + json.dumps(available, ensure_ascii=False)
            )

        def recency(document: Document) -> tuple[date, str]:
            document_date = document.period_end
            if document_date is None and document.published_at is not None:
                document_date = document.published_at.date()
            if document_date is None:
                document_date = document.fetched_at.date()
            return document_date, document.title

        document = max(documents, key=recency)
        provider = (
            OpenAICompatibleProvider(
                api_base_url=settings.research_api_base_url,
                api_key=settings.research_api_key,
                embedding_model=settings.embedding_model,
                research_model=settings.research_model,
                embedding_dimensions=settings.embedding_dimensions,
            )
            if settings.research_api_key
            else None
        )
        downloader = PrimaryDocumentDownloader(
            max_file_bytes=settings.document_max_file_bytes
        )
        try:
            ingestion = ingest_primary_document(
                session,
                document=document,
                ticker=ticker,
                downloader=downloader,
                storage_directory=settings.data_directory / "documents",
                embedding_provider=provider,
                trusted_document_hosts=tuple(
                    [*settings.configured_document_hosts, *args.allowed_document_host]
                ),
                embedding_dimensions=settings.embedding_dimensions,
            )
            evidence = DocumentRetriever(
                embedding_provider=provider,
                max_context_chars=settings.research_max_context_chars,
            ).retrieve(
                session,
                company_id=company.id,
                ticker=ticker,
                query=args.question,
                document_types=(args.document_type,),
                top_k=8,
            )
            answer = generate_grounded_answer(
                ticker=ticker,
                question=args.question,
                evidence=evidence,
                research_model=provider,
            )
        finally:
            downloader.close()
            if provider:
                provider.close()

        print(
            json.dumps(
                {
                    "discovery_status": discovered.status,
                    "selected_document": document.title,
                    "original_source_url": document.source_url,
                    "ingestion": {
                        "status": ingestion.status,
                        "pages": ingestion.page_count,
                        "chunks": ingestion.chunk_count,
                        "embedded_chunks": ingestion.embedded_chunk_count,
                        "period": ingestion.period_label,
                    },
                    "answer": answer.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    engine.dispose()


if __name__ == "__main__":
    main()
