from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finn_api.config import Settings
from finn_api.db.demo_seed import DEMO_USER_ID
from finn_api.db.models import User
from scripts.seed_demo_data import bind_demo_user


def _production_settings(**overrides) -> Settings:
    values = {
        "app_environment": "production",
        "database_url": "postgresql+psycopg://user:password@db.example.com/finn?sslmode=require",
        "cors_origins": "https://finn.example.com",
        "auth_jwks_url": "https://auth.example.com/.well-known/jwks.json",
        "auth_issuer": "https://auth.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_accept_remote_postgres_https_and_auth() -> None:
    assert _production_settings().production_configuration_errors() == ()


def test_production_settings_reject_local_database_and_origins() -> None:
    settings = _production_settings(
        database_url="postgresql+psycopg://localhost:5432/finn",
        cors_origins="http://localhost:3000",
    )

    assert settings.production_configuration_errors() == (
        "FINN_DATABASE_URL",
        "FINN_CORS_ORIGINS",
    )


def test_production_settings_reject_wildcard_origins() -> None:
    settings = _production_settings(cors_origins="https://*.vercel.app")

    assert settings.production_configuration_errors() == (
        "FINN_CORS_ORIGINS",
    )


def test_production_settings_require_database_tls() -> None:
    settings = _production_settings(
        database_url="postgresql+psycopg://user:password@db.example.com/finn"
    )

    assert settings.production_configuration_errors() == (
        "FINN_DATABASE_URL",
    )


def test_production_settings_require_valid_auth_issuer_and_jwks() -> None:
    settings = _production_settings(
        auth_jwks_url=None,
        auth_issuer="http://auth.example.com",
    )

    assert settings.production_configuration_errors() == (
        "FINN_AUTH_JWKS_URL",
        "FINN_AUTH_ISSUER",
    )


def test_development_settings_keep_local_defaults() -> None:
    settings = Settings(_env_file=None, app_environment="development")

    assert settings.production_configuration_errors() == ()


def test_demo_seed_binds_only_the_selected_existing_auth_subject() -> None:
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    auth_subject = uuid4()
    with Session(engine) as session:
        session.add(
            User(
                id=DEMO_USER_ID,
                auth_subject=DEMO_USER_ID,
                email="demo.user@finn.example",
                synthetic=True,
            )
        )
        session.commit()

        bind_demo_user(session, auth_subject)
        session.commit()
        assert session.get(User, DEMO_USER_ID).auth_subject == auth_subject
    engine.dispose()


def test_demo_seed_refuses_to_rebind_an_auth_subject_owned_by_another_user() -> None:
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    auth_subject = uuid4()
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id=DEMO_USER_ID,
                    auth_subject=DEMO_USER_ID,
                    email="demo.user@finn.example",
                    synthetic=True,
                ),
                User(
                    id=uuid4(),
                    auth_subject=auth_subject,
                    email="other.user@finn.example",
                    synthetic=True,
                ),
            ]
        )
        session.commit()

        with pytest.raises(ValueError, match="already associated"):
            bind_demo_user(session, auth_subject)
    engine.dispose()
