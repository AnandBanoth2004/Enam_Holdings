import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
sys.path.insert(0, str(backend_dir))

from finn_api.data_pipeline.company_documents import (  # noqa: E402
    CompanyDocumentDiscoveryService,
    persist_company_documents,
)
from finn_api.data_pipeline.validation import normalize_nse_ticker  # noqa: E402
from finn_api.db.engine import SessionLocal  # noqa: E402
from finn_api.db.models import CompanyAlias  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover primary documents on an issuer investor-relations website."
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--issuer-website")
    parser.add_argument(
        "--allowed-document-host",
        action="append",
        default=[],
        help="Additional company-authorized document host; may be supplied more than once.",
    )
    args = parser.parse_args()
    ticker = normalize_nse_ticker(args.ticker)

    service = CompanyDocumentDiscoveryService()
    try:
        result = service.discover(
            ticker,
            issuer_website=args.issuer_website,
            allowed_document_hosts=tuple(args.allowed_document_host),
        )
    finally:
        service.close()

    company_id: UUID | None = None
    with SessionLocal() as session:
        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == "NSE",
                CompanyAlias.normalized_symbol == ticker,
            )
        )
        if alias is not None:
            company_id = alias.company_id
        inserted = persist_company_documents(
            session,
            result,
            company_id=company_id,
        )
    print(
        f"{result.ticker}: {result.status}; documents={len(result.documents)}; "
        f"persisted={inserted}; primary_site={result.issuer_website or '-'}; "
        f"discovery_reference={result.discovery_reference or '-'}; "
        f"error={result.error_code or '-'}"
    )
    for document in result.documents:
        print(f"{document.document_type}: {document.title} — {document.source_url}")


if __name__ == "__main__":
    main()
