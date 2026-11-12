from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from finn_api.config import get_settings

database_url = get_settings().database_url
connection_options = (
    {"connect_timeout": 5}
    if database_url.startswith(("postgresql://", "postgresql+"))
    else {}
)
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args=connection_options,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
