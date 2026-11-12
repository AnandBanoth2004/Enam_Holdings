from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finn_api.api import health
from finn_api.db import models  # noqa: F401
from finn_api.db.base import Base
from finn_api.main import app


def test_root_reports_service_and_docs() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "FINN API", "docs": "/docs"}


def test_liveness_is_available_without_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_versioned_liveness_and_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_readiness_rejects_an_uninitialized_database_schema(monkeypatch) -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(health, "engine", test_engine)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    test_engine.dispose()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_schema_unavailable"


def test_readiness_accepts_an_initialized_database_schema(monkeypatch) -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    monkeypatch.setattr(health, "engine", test_engine)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    test_engine.dispose()
    assert response.status_code == 200
    assert response.json()["database"] == "available"


def test_database_metadata_contains_foundation_tables() -> None:
    assert {
        "companies",
        "company_aliases",
        "portfolios",
        "market_daily",
        "announcements",
        "documents",
        "document_chunks",
        "financial_periods",
        "workspaces",
        "network_people",
        "alert_rules",
        "research_runs",
        "ingestion_jobs",
    }.issubset(Base.metadata.tables)
    assert {
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "daily_change",
        "daily_change_pct",
        "average_volume_20",
        "volume_ratio",
    }.issubset(Base.metadata.tables["market_daily"].columns.keys())
    assert {
        "source_timestamp",
        "retrieval_status",
        "raw_document_path",
        "source_payload",
    }.issubset(Base.metadata.tables["announcements"].columns.keys())
