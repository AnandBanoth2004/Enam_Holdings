import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.engine import SessionLocal, engine
from finn_api.db.models import Company, CompanyAlias


def load_seed_file(
    session: Session,
    seed_file: Path,
    *,
    include_ad_hoc: bool = False,
    data_source_id=None,
) -> int:
    payload: Any = json.loads(seed_file.read_text(encoding="utf-8"))
    companies = payload.get("companies") if isinstance(payload, dict) else None
    if not isinstance(companies, list):
        raise ValueError("Seed file must contain a 'companies' list.")
    if include_ad_hoc:
        ad_hoc_companies = payload.get("ad_hoc_companies", [])
        if not isinstance(ad_hoc_companies, list):
            raise ValueError("'ad_hoc_companies' must be a list when provided.")
        companies = [*companies, *ad_hoc_companies]

    inserted_aliases = 0
    for row in companies:
        if not isinstance(row, dict):
            raise ValueError("Each company seed must be a JSON object.")

        legal_name = row.get("legal_name")
        display_name = row.get("display_name", legal_name)
        exchange = row.get("exchange")
        symbol = row.get("symbol")
        sector = row.get("sector")
        required_values = (legal_name, display_name, exchange, symbol)
        if not all(isinstance(value, str) and value.strip() for value in required_values):
            raise ValueError("Each company requires legal_name, display_name, exchange, and symbol.")
        if sector is not None and not isinstance(sector, str):
            raise ValueError("Company sector must be a string when provided.")

        legal_name = legal_name.strip()
        display_name = display_name.strip()
        exchange = exchange.strip().upper()
        symbol = symbol.strip().upper()

        company = session.scalar(select(Company).where(Company.legal_name == legal_name))
        if company is None:
            company = Company(
                legal_name=legal_name,
                display_name=display_name,
                sector=sector,
                data_source_id=data_source_id,
                synthetic=False,
            )
            session.add(company)
            session.flush()

        normalized_symbol = symbol.removesuffix(".NS").removesuffix(".BO")
        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == exchange,
                CompanyAlias.normalized_symbol == normalized_symbol,
            )
        )
        if alias is not None and alias.company_id != company.id:
            raise ValueError(
                f"{exchange}:{normalized_symbol} is already assigned to another company."
            )
        if alias is None:
            session.add(
                CompanyAlias(
                    company_id=company.id,
                    exchange=exchange,
                    symbol=symbol,
                    normalized_symbol=normalized_symbol,
                    alias=display_name,
                    data_source_id=data_source_id,
                    synthetic=False,
                )
            )
            inserted_aliases += 1

    session.commit()
    return inserted_aliases


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a vetted FINN JSON seed file.")
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    with SessionLocal() as session:
        inserted = load_seed_file(session, args.file)
    print(f"Seed complete: {inserted} new company aliases.")
    engine.dispose()


if __name__ == "__main__":
    main()
