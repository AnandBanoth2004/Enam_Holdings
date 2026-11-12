from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "FINN API"
    app_version: str = "0.1.0"
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    market_tickers: str = (
        "RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,ITC,LT,SBIN,"
        "BHARTIARTL,AXISBANK,KOTAKBANK,HINDUNILVR,BAJFINANCE,"
        "MARUTI,SUNPHARMA,TATAMOTORS,TITAN,ASIANPAINT"
    )
    market_cache_ttl_seconds: int = 21600
    research_api_base_url: str = "https://api.openai.com/v1"
    research_api_key: str | None = None
    research_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    document_max_file_bytes: int = 30 * 1024 * 1024
    document_allowed_hosts: str = ""
    research_max_context_chars: int = 18000
    research_retrieval_cache_seconds: int = 300
    auth_jwks_url: str | None = None
    auth_issuer: str | None = None
    auth_audience: str = "authenticated"
    data_directory: Path = REPOSITORY_ROOT / "data"
    database_url: str = "postgresql+psycopg://localhost:54322/postgres"

    model_config = SettingsConfigDict(
        env_prefix="FINN_",
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def configured_market_tickers(self) -> tuple[str, ...]:
        return tuple(
            ticker.strip().upper().removesuffix(".NS")
            for ticker in self.market_tickers.split(",")
            if ticker.strip()
        )

    @property
    def configured_document_hosts(self) -> tuple[str, ...]:
        return tuple(
            host.strip().casefold().strip(".")
            for host in self.document_allowed_hosts.split(",")
            if host.strip()
        )

    def production_configuration_errors(self) -> tuple[str, ...]:
        if self.app_environment.casefold() not in {"prod", "production"}:
            return ()

        errors: list[str] = []
        try:
            database_url = make_url(self.database_url)
            if (
                not database_url.drivername.startswith("postgresql")
                or not database_url.host
                or database_url.host.casefold() in {"localhost", "127.0.0.1", "::1"}
                or not database_url.database
                or database_url.query.get("sslmode", "").casefold()
                not in {"require", "verify-ca", "verify-full"}
            ):
                errors.append("FINN_DATABASE_URL")
        except (ArgumentError, TypeError, ValueError):
            errors.append("FINN_DATABASE_URL")

        origins = self.allowed_origins
        if not origins:
            errors.append("FINN_CORS_ORIGINS")
        else:
            for origin in origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                    or parsed.username
                    or parsed.password
                    or "*" in parsed.hostname
                    or parsed.hostname.casefold()
                    in {"localhost", "127.0.0.1", "::1"}
                ):
                    errors.append("FINN_CORS_ORIGINS")
                    break

        for name, value in (
            ("FINN_AUTH_JWKS_URL", self.auth_jwks_url),
            ("FINN_AUTH_ISSUER", self.auth_issuer),
        ):
            parsed = urlsplit(value or "")
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
            ):
                errors.append(name)

        return tuple(errors)


@lru_cache
def get_settings() -> Settings:
    return Settings()
