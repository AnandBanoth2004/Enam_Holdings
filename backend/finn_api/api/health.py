import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from finn_api.config import get_settings
from finn_api.db.engine import engine
from finn_api.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
_REQUIRED_TABLES = {
    "announcements",
    "companies",
    "document_chunks",
    "documents",
    "market_daily",
    "portfolios",
    "users",
    "workspaces",
}


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service=get_settings().app_name)


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            missing_tables = _REQUIRED_TABLES - set(
                inspect(connection).get_table_names()
            )
    except SQLAlchemyError as error:
        logger.warning("Readiness check failed: database unavailable (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "The database is not reachable.",
            },
        ) from error

    if missing_tables:
        logger.warning(
            "Readiness check failed: required database tables are missing (%s)",
            ", ".join(sorted(missing_tables)),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_schema_unavailable",
                "message": "The database schema is not initialized.",
            },
        )

    return ReadinessResponse(
        status="ok",
        service=get_settings().app_name,
        database="available",
    )
