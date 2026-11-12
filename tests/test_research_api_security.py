from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finn_api.db.base import Base
from finn_api.db.engine import get_db_session
from finn_api.main import app


def test_public_company_search_remains_available_without_authentication() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/research/companies/search",
                params={"q": "RELIANCE"},
            )
        assert response.status_code == 200
        assert response.json()["results"] == []
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_expensive_or_mutating_research_endpoints_require_authentication() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    document_id = "00000000-0000-0000-0000-000000000001"
    endpoints = (
        (
            "/api/v1/research/discover",
            {"ticker": "RELIANCE"},
        ),
        (
            f"/api/v1/research/documents/{document_id}/ingest",
            {},
        ),
        (
            f"/api/v1/research/documents/{document_id}/extract-financials",
            {
                "period_label": "Q1 FY2026",
                "period_start": "2025-04-01",
                "period_end": "2025-06-30",
                "period_type": "quarter",
                "reporting_basis": "consolidated",
                "currency": "INR",
                "unit_scale": "crore",
            },
        ),
        (
            "/api/v1/research/answer",
            {"ticker": "RELIANCE", "question": "Summarize cash flow"},
        ),
    )
    try:
        with TestClient(app) as client:
            for path, body in endpoints:
                response = client.post(path, json=body)
                assert response.status_code == 401, (path, response.text)
                assert response.json()["error"]["code"] == "authentication_required"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
