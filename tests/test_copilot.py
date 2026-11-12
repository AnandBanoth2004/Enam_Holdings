from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finn_api.api.auth import get_current_user
from finn_api.copilot.service import classify_query
from finn_api.data_pipeline.network_seed import (
    load_synthetic_contact_dataset,
    seed_synthetic_contacts,
)
from finn_api.db.base import Base
from finn_api.db.engine import get_db_session
from finn_api.db.models import (
    Announcement,
    AlertRule,
    Company,
    CompanyAlias,
    MarketDaily,
    Portfolio,
    PortfolioCompany,
    User,
    Workspace,
    WorkspaceMember,
)
from finn_api.main import app

ROOT = Path(__file__).resolve().parents[1]
NETWORK_DATASET = ROOT / "data" / "fixtures" / "network_contacts.json"


def _client_with_data():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    workspace_id = uuid4()
    user = User(auth_subject=uuid4(), email=f"{uuid4()}@example.test")
    other_user = User(auth_subject=uuid4(), email=f"{uuid4()}@example.test")
    workspace = Workspace(name="Copilot test workspace", synthetic=True)
    company = Company(
        legal_name="Reliance Industries Limited",
        display_name="Reliance Industries",
        sector="Energy",
        synthetic=False,
    )
    with Session(engine) as session:
        session.add_all((user, other_user, workspace, company))
        session.flush()
        session.add_all(
            (
                WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"),
                WorkspaceMember(workspace_id=workspace.id, user_id=other_user.id, role="viewer"),
                Portfolio(
                    id=uuid4(),
                    workspace_id=workspace.id,
                    name="Demo",
                    is_default=True,
                    synthetic=True,
                ),
                CompanyAlias(
                    company_id=company.id,
                    exchange="NSE",
                    symbol="RELIANCE.NS",
                    normalized_symbol="RELIANCE",
                    synthetic=False,
                ),
            )
        )
        session.flush()
        portfolio = session.scalar(
            select(Portfolio).where(Portfolio.workspace_id == workspace.id)
        )
        assert portfolio is not None
        session.add(PortfolioCompany(portfolio_id=portfolio.id, company_id=company.id))
        session.add(
            Announcement(
                company_id=company.id,
                source="synthetic_fixture",
                source_key=f"copilot-{uuid4()}",
                source_url="https://example.test/fictional-filing",
                headline="[DEMO ONLY] Fictional capacity expansion",
                body_text="Fictional company announcement for the Copilot integration test.",
                filed_at=datetime.now(timezone.utc),
                category="capex",
                materiality="high",
                materiality_score=74,
                materiality_reasons=["Fictional materiality rule"],
                summary="A fictional expansion filing.",
                fetched_at=datetime.now(timezone.utc),
                synthetic=True,
            )
        )
        seed_synthetic_contacts(
            session,
            workspace_id=workspace.id,
            dataset=load_synthetic_contact_dataset(NETWORK_DATASET),
        )
        session.commit()
        workspace_id_value = workspace.id
        user_id = user.id
        other_user_id = other_user.id

    def override_session():
        with Session(engine) as session:
            yield session

    def override_user():
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), engine, workspace_id_value, user_id, other_user_id


def test_query_classification_routes_all_layers_and_cross_layer():
    push = classify_query("What happened in my portfolio today?")
    assert push.intent == "push_digest"
    assert push.layers == ("push",)

    network = classify_query("Who in my network understands the banking sector?")
    assert network.intent == "network_expertise"
    assert network.expertise == "banking"

    cross = classify_query(
        "A new CFO joined Reliance. Who in my network might know them?"
    )
    assert cross.intent == "network_executive_diligence"
    assert cross.ticker is None

    unusual_volume = classify_query("Show unusual volume movements")
    assert unusual_volume.intent == "push_market_movement"
    assert unusual_volume.layers == ("push",)

    financial = classify_query("How has revenue changed over the last four quarters for RELIANCE?")
    assert financial.intent == "pull_financial_trajectory"

    portfolio_context = classify_query(
        "Which portfolio companies have important developments and who can explain them?"
    )
    assert portfolio_context.intent == "cross_portfolio_context"
    assert portfolio_context.layers == ("push", "network")


def test_copilot_resolves_company_runs_push_and_stores_private_history():
    client, engine, workspace_id, user_id, other_user_id = _client_with_data()
    try:
        response = client.post(
            "/api/v1/copilot/query",
            json={
                "workspace_id": str(workspace_id),
                "query": "I am researching Reliance Industries. What are the important announcements and who can provide context?",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["intent"] == "cross_company_context"
        assert payload["layers"] == ["push", "pull", "network"]
        push_block = next(block for block in payload["blocks"] if block["layer"] == "push")
        assert push_block["data"]["announcements"][0]["is_synthetic"] is True
        assert push_block["citations"][0]["source_url"] == "https://example.test/fictional-filing"
        assert any(tool["name"] == "primary_source_rag" for tool in payload["tools"])

        history = client.get(
            f"/api/v1/copilot/conversations/{payload['conversation_id']}",
            params={"workspace_id": str(workspace_id)},
        )
        assert history.status_code == 200
        assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant"]
        assert history.json()["messages"][1]["result"]["message_id"] == payload["message_id"]

        with Session(engine) as session:
            from finn_api.db.models import CopilotConversation

            conversation = session.scalar(
                select(CopilotConversation).where(
                    CopilotConversation.id == UUID(payload["conversation_id"])
                )
            )
            assert conversation is not None
            assert conversation.user_id == user_id
            assert conversation.user_id != other_user_id
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_conversation_id_cannot_be_reused_by_another_user():
    client, engine, workspace_id, _, other_user_id = _client_with_data()
    try:
        first = client.post(
            "/api/v1/copilot/query",
            json={
                "workspace_id": str(workspace_id),
                "query": "What happened in my portfolio today?",
            },
        )
        assert first.status_code == 200
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=other_user_id)
        response = client.post(
            "/api/v1/copilot/query",
            json={
                "workspace_id": str(workspace_id),
                "conversation_id": first.json()["conversation_id"],
                "query": "Show today's portfolio announcements",
            },
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_missing_company_returns_clarification_without_claiming_research():
    client, engine, workspace_id, _, _ = _client_with_data()
    try:
        response = client.post(
            "/api/v1/copilot/query",
            json={
                "workspace_id": str(workspace_id),
                "query": "Analyse an unsupported issuer",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "pull_research"
        assert payload["blocks"] == []
        assert payload["tools"] == []
        assert "Which NSE company" in payload["answer"]
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_conversation_list_and_delete_are_scoped_to_user_and_workspace():
    client, engine, workspace_id, user_id, other_user_id = _client_with_data()
    try:
        from finn_api.db.models import CopilotConversation, CopilotMessage

        created = client.post(
            "/api/v1/copilot/query",
            json={
                "workspace_id": str(workspace_id),
                "query": "What happened in my portfolio today?",
            },
        )
        assert created.status_code == 200
        conversation_id = created.json()["conversation_id"]
        with Session(engine) as session:
            for index in range(2):
                created_at = datetime.now(timezone.utc) - timedelta(days=index + 1)
                conversation = CopilotConversation(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    title=f"Older test conversation {index}",
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(conversation)
                session.flush()
                session.add(
                    CopilotMessage(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=f"Preview {index}",
                        created_at=created_at,
                    )
                )
            session.commit()

        message_queries: list[str] = []

        def capture_message_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
            if "copilot_messages" in statement.casefold():
                message_queries.append(statement)

        event.listen(engine, "before_cursor_execute", capture_message_queries)
        listed = client.get(
            "/api/v1/copilot/conversations",
            params={"workspace_id": str(workspace_id)},
        )
        event.remove(engine, "before_cursor_execute", capture_message_queries)
        assert listed.status_code == 200
        assert listed.headers["cache-control"] == "private, no-store"
        assert [item["id"] for item in listed.json()["conversations"]][0] == conversation_id
        assert len(listed.json()["conversations"]) == 3
        assert len(message_queries) == 1

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=other_user_id)
        other_user_list = client.get(
            "/api/v1/copilot/conversations",
            params={"workspace_id": str(workspace_id)},
        )
        assert other_user_list.status_code == 200
        assert other_user_list.json()["conversations"] == []
        denied_delete = client.delete(
            f"/api/v1/copilot/conversations/{conversation_id}",
            params={"workspace_id": str(workspace_id)},
        )
        assert denied_delete.status_code == 404

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
        deleted = client.delete(
            f"/api/v1/copilot/conversations/{conversation_id}",
            params={"workspace_id": str(workspace_id)},
        )
        assert deleted.status_code == 204
        missing = client.get(
            f"/api/v1/copilot/conversations/{conversation_id}",
            params={"workspace_id": str(workspace_id)},
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_unusual_volume_requires_and_applies_configured_threshold():
    client, engine, workspace_id, _, _ = _client_with_data()
    try:
        with Session(engine) as session:
            portfolio = session.scalar(
                select(Portfolio).where(
                    Portfolio.workspace_id == workspace_id,
                    Portfolio.is_default.is_(True),
                )
            )
            company = session.scalar(
                select(Company).where(Company.display_name == "Reliance Industries")
            )
            assert portfolio is not None and company is not None
            session.add(
                MarketDaily(
                    company_id=company.id,
                    exchange="NSE",
                    market_date=date(2026, 11, 10),
                    close=Decimal("990"),
                    volume=3500,
                    average_volume_20=Decimal("1000"),
                    volume_ratio=Decimal("3.5"),
                    source="synthetic_fixture",
                    fetched_at=datetime.now(timezone.utc) - timedelta(days=1),
                    synthetic=True,
                )
            )
            session.add(
                MarketDaily(
                    company_id=company.id,
                    exchange="NSE",
                    market_date=date(2026, 11, 11),
                    close=Decimal("1000"),
                    volume=2000,
                    average_volume_20=Decimal("1000"),
                    volume_ratio=Decimal("2"),
                    source="synthetic_fixture",
                    fetched_at=datetime.now(timezone.utc),
                    synthetic=True,
                )
            )
            session.commit()

        payload = {
            "workspace_id": str(workspace_id),
            "query": "Show unusual volume movements",
        }
        no_rule = client.post("/api/v1/copilot/query", json=payload)
        assert no_rule.status_code == 200
        no_rule_result = no_rule.json()
        assert no_rule_result["blocks"][0]["data"]["movements"] == []
        assert any("Configure a volume-movement" in item for item in no_rule_result["limitations"])

        with Session(engine) as session:
            portfolio = session.scalar(
                select(Portfolio).where(Portfolio.workspace_id == workspace_id)
            )
            company = session.scalar(
                select(Company).where(Company.display_name == "Reliance Industries")
            )
            assert portfolio is not None and company is not None
            session.add(
                AlertRule(
                    workspace_id=workspace_id,
                    portfolio_id=portfolio.id,
                    company_id=company.id,
                    rule_type="volume_move",
                    enabled=True,
                    volume_multiplier=Decimal("1.5"),
                    is_synthetic=True,
                )
            )
            session.commit()

        configured = client.post("/api/v1/copilot/query", json=payload)
        assert configured.status_code == 200
        movement_block = configured.json()["blocks"][0]
        assert movement_block["data"]["thresholds_configured"] is True
        assert len(movement_block["data"]["movements"]) == 1
        assert movement_block["data"]["movements"][0]["date"] == "2026-11-11"
        assert Decimal(movement_block["data"]["movements"][0]["volume_ratio"]) == Decimal("2")
        assert Decimal(
            movement_block["data"]["movements"][0]["configured_volume_threshold"]
        ) == Decimal("1.5")
        assert movement_block["data"]["movements"][0]["is_synthetic"] is True
    finally:
        app.dependency_overrides.clear()
        client.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
