import argparse
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
sys.path.insert(0, str(backend_dir))

from finn_api.config import get_settings  # noqa: E402
from finn_api.db import models  # noqa: E402,F401
from finn_api.db.base import Base  # noqa: E402
from finn_api.db.demo_seed import seed_demo_database  # noqa: E402
from finn_api.db.engine import SessionLocal, engine  # noqa: E402


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_reset_target(*, confirmed: bool, environment: str, database_url: str) -> None:
    if not confirmed:
        raise ValueError("Pass --confirm-reset to authorize destructive database reset.")
    if environment.casefold() in {"prod", "production"}:
        raise ValueError("Refusing to reset a production environment.")

    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("Demo reset is supported only against a local PostgreSQL database.")
    if url.host not in LOCAL_HOSTS:
        raise ValueError("Refusing to reset a non-local PostgreSQL database.")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Destructively reset the local FINN application database and seed demo data."
    )
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Required acknowledgement: FINN application tables will be dropped.",
    )
    args = parser.parse_args()

    validate_reset_target(
        confirmed=args.confirm_reset,
        environment=settings.app_environment,
        database_url=settings.database_url,
    )

    Base.metadata.drop_all(bind=engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        check=True,
    )
    with SessionLocal() as session:
        counts = seed_demo_database(session, settings.data_directory)

    print("FINN local demo database reset and seed completed.")
    for key, value in counts.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
