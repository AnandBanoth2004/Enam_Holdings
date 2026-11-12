import pytest

from scripts.reset_and_seed_demo import validate_reset_target


LOCAL_DATABASE_URL = "postgresql+psycopg://demo:demo@127.0.0.1:54322/postgres"


def test_reset_guard_requires_explicit_acknowledgement() -> None:
    with pytest.raises(ValueError, match="--confirm-reset"):
        validate_reset_target(
            confirmed=False,
            environment="development",
            database_url=LOCAL_DATABASE_URL,
        )


@pytest.mark.parametrize("environment", ["production", "prod", "PRODUCTION"])
def test_reset_guard_rejects_production(environment: str) -> None:
    with pytest.raises(ValueError, match="production"):
        validate_reset_target(
            confirmed=True,
            environment=environment,
            database_url=LOCAL_DATABASE_URL,
        )


def test_reset_guard_rejects_remote_postgres_and_non_postgres() -> None:
    with pytest.raises(ValueError, match="non-local"):
        validate_reset_target(
            confirmed=True,
            environment="development",
            database_url="postgresql+psycopg://demo:demo@example.com/postgres",
        )
    with pytest.raises(ValueError, match="local PostgreSQL"):
        validate_reset_target(
            confirmed=True,
            environment="development",
            database_url="sqlite:///demo.db",
        )


def test_reset_guard_accepts_only_confirmed_local_nonproduction_postgres() -> None:
    validate_reset_target(
        confirmed=True,
        environment="development",
        database_url=LOCAL_DATABASE_URL,
    )
