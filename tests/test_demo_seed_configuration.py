import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finn_api.config import Settings
from finn_api.db.models import Company, CompanyAlias
from finn_api.db.seed import load_seed_file

ROOT = Path(__file__).resolve().parents[1]


def test_default_nse_market_universe_is_configurable_and_has_18_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FINN_MARKET_TICKERS", raising=False)
    default = Settings().configured_market_tickers
    override = Settings(market_tickers="newco,other.ns").configured_market_tickers

    assert len(default) == 18
    assert len(set(default)) == 18
    assert override == ("NEWCO", "OTHER")


def test_demo_company_seed_has_18_idempotent_nse_aliases() -> None:
    seed_path = ROOT / "data" / "seed" / "demo_seed.json"
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    assert len(payload["companies"]) == 18
    assert "not an official" in payload["note"]

    engine = create_engine("sqlite://")
    Company.__table__.create(engine)
    CompanyAlias.__table__.create(engine)
    with Session(engine) as session:
        assert load_seed_file(session, seed_path) == 18
        assert load_seed_file(session, seed_path) == 0
        assert session.scalar(select(func.count()).select_from(Company)) == 18
        assert session.scalar(select(func.count()).select_from(CompanyAlias)) == 18
    engine.dispose()
