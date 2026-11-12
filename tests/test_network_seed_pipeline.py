import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.network_seed import (
    SyntheticDatasetError,
    load_synthetic_contact_dataset,
    seed_synthetic_contacts,
)
from finn_api.db.models import (
    Company,
    CompanyAlias,
    NetworkEdge,
    NetworkPerson,
    NetworkRelationship,
    PersonExperience,
    Workspace,
)
from finn_api.db.base import Base

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "fixtures" / "network_contacts.json"


def test_dataset_has_30_to_50_fictional_profiles_and_portfolio_overlap() -> None:
    dataset = load_synthetic_contact_dataset(DATASET)
    tickers = {
        experience.ticker
        for profile in dataset.profiles
        for experience in profile.experiences
        if experience.ticker
    }
    sectors = {experience.sector for profile in dataset.profiles for experience in profile.experiences}
    competitor_experiences = [
        experience
        for profile in dataset.profiles
        for experience in profile.experiences
        if experience.ticker is None
    ]

    assert 30 <= len(dataset.profiles) <= 50
    assert all(profile.display_name for profile in dataset.profiles)
    assert {"RELIANCE", "TCS", "HDFCBANK", "ASIANPAINT"}.issubset(tickers)
    assert len(sectors) >= 8
    assert competitor_experiences
    assert "fictional" in dataset.notice.casefold()


def test_contact_loader_rejects_non_synthetic_profiles(tmp_path) -> None:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    payload["profiles"][0]["synthetic"] = False
    bad_file = tmp_path / "contacts.json"
    bad_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SyntheticDatasetError, match="marked synthetic"):
        load_synthetic_contact_dataset(bad_file)


def test_network_seed_is_workspace_scoped_and_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    workspace_id = uuid4()
    with Session(engine) as session:
        workspace = Workspace(id=workspace_id, name="Synthetic test workspace")
        session.add(workspace)
        company = Company(legal_name="Reliance Industries Limited", display_name="Reliance")
        session.add(company)
        session.flush()
        session.add(
            CompanyAlias(
                company_id=company.id,
                exchange="NSE",
                symbol="RELIANCE.NS",
                normalized_symbol="RELIANCE",
            )
        )
        session.commit()

        dataset = load_synthetic_contact_dataset(DATASET)
        assert seed_synthetic_contacts(
            session, workspace_id=workspace_id, dataset=dataset
        ) == 36
        assert seed_synthetic_contacts(
            session, workspace_id=workspace_id, dataset=dataset
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(NetworkPerson).where(
                NetworkPerson.workspace_id == workspace_id,
                NetworkPerson.source_type == "synthetic_fixture",
            )
        ) == 36
        assert session.scalar(
            select(func.count()).select_from(PersonExperience).where(
                PersonExperience.workspace_id == workspace_id
            )
        ) >= 36  # at least 1 experience per profile; enriched profiles have multiple
        reliance_contact_experience = session.scalar(
            select(PersonExperience).where(PersonExperience.company_id == company.id)
        )
        assert reliance_contact_experience is not None
        assert reliance_contact_experience.source_label.startswith("synthetic_fixture:")
        assert session.scalar(
            select(func.count()).select_from(NetworkEdge).where(
                NetworkEdge.workspace_id == workspace_id,
                NetworkEdge.edge_type == "synthetic_peer",
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(NetworkRelationship).where(
                NetworkRelationship.workspace_id == workspace_id,
            )
        ) == 9
    engine.dispose()
