import json
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finn_api.api.auth import get_current_user
from finn_api.data_pipeline.network_seed import (
    load_synthetic_contact_dataset,
    seed_synthetic_contacts,
)
from finn_api.db.base import Base
from finn_api.db.engine import get_db_session
from finn_api.db.models import (
    Announcement,
    Company,
    CompanyAlias,
    EntityMatch,
    NetworkPerson,
    ResearchReport,
    User,
    Workspace,
    WorkspaceMember,
)
from finn_api.main import app
from finn_api.network.matching import EntityCandidate, match_company_name, match_contact_name

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "fixtures" / "network_contacts.json"


def _client_with_network_data():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    workspace_id = uuid4()
    user = User(auth_subject=uuid4(), email=f"{uuid4()}@example.test")
    other_workspace = Workspace(name="Other private workspace")
    workspace = Workspace(id=workspace_id, name="Synthetic test workspace", synthetic=True)
    icici = Company(legal_name="ICICI Bank Limited", display_name="ICICI Bank", sector="Financial Services")
    tcs = Company(legal_name="Tata Consultancy Services Limited", display_name="TCS", sector="Information Technology")
    with Session(engine) as session:
        session.add_all((user, workspace, other_workspace, icici, tcs))
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
        )
        session.add(
            ResearchReport(
                workspace_id=workspace.id,
                company_id=tcs.id,
                report_key="network-executive-demo",
                title="Synthetic TCS management diligence report",
                status="partial",
                summary="Synthetic research report naming fictional executive Kabir Rao.",
                content={"management_diligence": {"candidate_name": "Kabir Rao"}},
                is_synthetic=True,
            )
        )
        session.add_all(
            [
                CompanyAlias(
                    company_id=icici.id,
                    exchange="NSE",
                    symbol="ICICIBANK.NS",
                    normalized_symbol="ICICIBANK",
                ),
                CompanyAlias(
                    company_id=tcs.id,
                    exchange="NSE",
                    symbol="TCS.NS",
                    normalized_symbol="TCS",
                ),
                Announcement(
                    company_id=icici.id,
                    source="synthetic_fixture",
                    source_key="network-management-executive",
                    source_url="https://example.test/fictional-announcement",
                    headline="[DEMO ONLY] Fictional appointment of Mira Deshpande as chief strategy officer",
                    body_text="Mira Deshpande is not a real executive; this is a synthetic demo fixture.",
                    filed_at=datetime(2025, 12, 1),
                    fetched_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
                    category="management_change",
                    synthetic=True,
                ),
            ]
        )
        session.flush()
        seed_synthetic_contacts(
            session,
            workspace_id=workspace.id,
            dataset=load_synthetic_contact_dataset(DATASET),
        )
        user_id = user.id
        other_workspace_id = other_workspace.id
        company_ids = (icici.id, tcs.id)
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    def override_user():
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), engine, workspace_id, user_id, other_workspace_id, company_ids


def test_missing_identity_and_cross_workspace_requests_are_denied():
    client, engine, workspace_id, user_id, other_workspace_id, _ = _client_with_network_data()
    try:
        app.dependency_overrides.pop(get_current_user, None)
        unauthenticated = client.get(
            "/api/v1/network/contacts",
            params={"workspace_id": str(workspace_id)},
        )
        assert unauthenticated.status_code == 401

        with Session(engine) as session:
            user = session.get(User, user_id)
            assert user is not None
            from finn_api.api.auth import require_workspace_membership

            try:
                require_workspace_membership(
                    session,
                    workspace_id=other_workspace_id,
                    user=user,
                )
            except Exception as error:
                assert getattr(error, "status_code", None) == 403
            else:
                raise AssertionError("A non-member must not access the workspace.")
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_network_search_paths_company_and_management_recommendation():
    client, engine, workspace_id, _, _, company_ids = _client_with_network_data()
    try:
        params = {"workspace_id": str(workspace_id)}
        contacts_response = client.get("/api/v1/network/contacts", params=params)
        assert contacts_response.status_code == 200
        contacts = contacts_response.json()["contacts"]
        mira = next(item for item in contacts if item["display_name"] == "Mira Deshpande")
        assert mira["is_synthetic"] is True
        assert mira["current_role"] == "Infrastructure Strategy Lead"
        assert mira["connection_distance"] == 1
        assert mira["relationship_evidence"].startswith("Fictional demo fixture")

        second_degree = client.get("/api/v1/network/second-degree", params=params)
        assert second_degree.status_code == 200
        kabir = next(
            item
            for item in second_degree.json()["contacts"]
            if item["display_name"] == "Kabir Rao"
        )
        assert kabir["connection_distance"] == 2

        path = client.get(
            f"/api/v1/network/paths/{kabir['id']}",
            params=params,
        )
        assert path.status_code == 200
        assert path.json()["distance"] == 2
        assert [step["name"] for step in path.json()["path"]] == [
            "Aarav Mehta",
            "Kabir Rao",
        ]

        company = client.get("/api/v1/network/companies/TCS/connections", params=params)
        assert company.status_code == 200
        assert company.json()["match_confidence"] == 1.0
        assert any(
            item["display_name"] == "Kabir Rao"
            for item in company.json()["contacts"]
        )
        kabir_match = next(
            item
            for item in company.json()["entity_matches"]
            if item["contact_name"] == "Kabir Rao"
        )
        assert kabir_match["confidence"] == 1.0
        assert kabir_match["status"] == "accepted"
        assert "does not establish a personal relationship" in kabir_match["evidence"]

        recommendations = client.get(
            "/api/v1/network/recommendations",
            params={
                **params,
                "workflow": "management_diligence",
                "ticker": "ICICIBANK",
            },
        )
        assert recommendations.status_code == 200
        result = recommendations.json()
        assert result["recommendations"][0]["contact"]["display_name"] == "Mira Deshpande"
        assert result["recommendations"][0]["evidence_quality"] == "explicit_synthetic_fixture"
        assert "fictional" in result["notice"].casefold()
        assert any(
            "announcement:" in reason
            for reason in result["recommendations"][0]["reasons"]
        )
        with Session(engine) as session:
            match = session.scalar(
                select(func.count()).select_from(EntityMatch).where(
                    EntityMatch.workspace_id == workspace_id,
                    EntityMatch.person_id == UUID(mira["id"]),
                )
            )
            assert match >= 1

        report_recommendations = client.get(
            "/api/v1/network/recommendations",
            params={
                **params,
                "workflow": "management_diligence",
                "ticker": "TCS",
            },
        )
        assert report_recommendations.status_code == 200
        report_result = report_recommendations.json()["recommendations"]
        kabir_recommendation = next(
            item
            for item in report_result
            if item["contact"]["display_name"] == "Kabir Rao"
        )
        assert any(
            "research_report:" in reason
            for reason in kabir_recommendation["reasons"]
        )
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_cross_workspace_contact_id_is_not_visible():
    client, engine, workspace_id, _, other_workspace_id, _ = _client_with_network_data()
    try:
        with Session(engine) as session:
            contact = session.scalar(
                select(NetworkPerson).where(
                    NetworkPerson.workspace_id == workspace_id,
                    NetworkPerson.source_type == "synthetic_fixture",
                )
            )
            assert contact is not None
            response = client.get(
                f"/api/v1/network/contacts/{contact.id}",
                params={"workspace_id": str(other_workspace_id)},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_entity_matching_requires_strong_evidence_and_keeps_fuzzy_proposals():
    contact_candidates = [
        EntityCandidate("1", "Mira Deshpande"),
        EntityCandidate("2", "Mira Deshpandey"),
    ]
    assert match_contact_name("Mira Deshpande", contact_candidates)[0].method == "exact"
    assert match_contact_name("Mira", contact_candidates) == []
    assert match_contact_name("Mira Deshpand", contact_candidates)[0].method == "fuzzy_proposed"

    company_matches = match_company_name(
        "Tata Consultancy Services Limited",
        [
            EntityCandidate("1", "Tata Consultancy Services Ltd."),
            EntityCandidate("2", "Tata Consumer Products Limited"),
        ],
    )
    assert company_matches[0].method == "exact"
    assert company_matches[0].candidate_id == "1"


def test_synthetic_fixture_relationships_must_be_explicit():
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    payload["direct_connections"] = []
    invalid = ROOT / "data" / "fixtures" / "_invalid_network_test.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")
    try:
        from finn_api.data_pipeline.network_seed import SyntheticDatasetError

        try:
            load_synthetic_contact_dataset(invalid)
        except SyntheticDatasetError as error:
            assert "explicit investor relationships" in str(error)
        else:
            raise AssertionError("Missing explicit relationship evidence should be rejected.")
    finally:
        invalid.unlink(missing_ok=True)
