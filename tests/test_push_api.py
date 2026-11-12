from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from uuid import uuid4
from types import SimpleNamespace

from finn_api.api.auth import get_current_user
from finn_api.db.base import Base
from finn_api.db.engine import get_db_session
from finn_api.db.models import Alert, Company, User, Workspace, WorkspaceMember
from finn_api.main import app


def test_push_classification_api_returns_category_score_and_reasons() -> None:
    user = User(id=uuid4(), auth_subject=uuid4())
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/push/classify",
            json={
                "headline": "Board approves acquisition of a subsidiary for INR 250 crore",
                "body": "The issuer is part of the monitored portfolio.",
                "is_portfolio_company": True,
            },
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    result = response.json()
    assert result["category"] == "M&A"
    assert result["materiality_score"] == 75
    assert result["priority"] == "high"
    assert result["method"] == "deterministic_rules_v1"
    assert result["reasons"]
    assert any("250 crore" in reason for reason in result["reasons"])


def test_push_digest_route_requires_custom_range_dates() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    user = User(id=uuid4(), auth_subject=uuid4())
    workspace = Workspace(name="Digest test workspace")
    with Session(engine) as session:
        session.add_all((user, workspace))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        session.commit()
        workspace_id = workspace.id
        user_id = user.id

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/push/digest",
                params={"workspace_id": str(workspace_id), "window": "custom"},
            )
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_digest_window"


def test_push_routes_are_in_openapi() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert {
        "/api/v1/push/digest",
        "/api/v1/push/announcements/{announcement_id}",
        "/api/v1/push/announcements/{announcement_id}/materiality",
        "/api/v1/push/classify",
        "/api/v1/push/alerts/config",
        "/api/v1/push/alerts/history",
        "/api/v1/push/alerts/{alert_id}/status",
        "/api/v1/push/alerts/evaluate",
        "/api/v1/push/results/{ticker}/comparisons",
    }.issubset(paths)
    assert "put" in paths["/api/v1/push/alerts/config"]
    assert "patch" in paths["/api/v1/push/alerts/{alert_id}/status"]


def test_alert_status_api_persists_read_and_unread() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workspace = Workspace(name="Alert status test")
        company = Company(legal_name="Alert Status Ltd", display_name="Alert Status")
        session.add_all((workspace, company))
        session.flush()
        user = User(id=uuid4(), auth_subject=uuid4())
        session.add(user)
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        alert = Alert(
            workspace_id=workspace.id,
            company_id=company.id,
            alert_type="announcement",
            title="Demo alert",
            status="unread",
            dedupe_key="alert-status-test",
            is_synthetic=True,
        )
        session.add(alert)
        session.commit()
        workspace_id = workspace.id
        alert_id = alert.id
        user_id = user.id

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    try:
        with TestClient(app) as client:
            read_response = client.patch(
                f"/api/v1/push/alerts/{alert_id}/status",
                json={"workspace_id": str(workspace_id), "status": "read"},
            )
            unread_response = client.patch(
                f"/api/v1/push/alerts/{alert_id}/status",
                json={"workspace_id": str(workspace_id), "status": "unread"},
            )
        assert read_response.status_code == 200
        assert read_response.json()["status"] == "read"
        assert read_response.json()["is_synthetic"] is True
        assert unread_response.status_code == 200
        assert unread_response.json()["status"] == "unread"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_push_workspace_access_is_required_for_digest_and_alert_updates() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workspace = Workspace(name="Private workspace")
        other_workspace = Workspace(name="Another private workspace")
        user = User(id=uuid4(), auth_subject=uuid4())
        company = Company(legal_name="Private Alert Ltd", display_name="Private Alert")
        session.add_all((workspace, other_workspace, user, company))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        alert = Alert(
            workspace_id=workspace.id,
            company_id=company.id,
            alert_type="announcement",
            title="Private alert",
            status="unread",
            dedupe_key="private-alert",
            is_synthetic=True,
        )
        session.add(alert)
        session.commit()
        workspace_id, other_workspace_id, user_id, alert_id = (
            workspace.id,
            other_workspace.id,
            user.id,
            alert.id,
        )

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    try:
        with TestClient(app) as client:
            denied_digest = client.get(
                "/api/v1/push/digest",
                params={"workspace_id": str(other_workspace_id)},
            )
            denied_update = client.patch(
                f"/api/v1/push/alerts/{alert_id}/status",
                json={"workspace_id": str(other_workspace_id), "status": "read"},
            )
        assert denied_digest.status_code == 403
        assert denied_update.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
