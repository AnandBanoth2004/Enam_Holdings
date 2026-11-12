from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from finn_api.config import get_settings  # noqa: E402
from finn_api.db.demo_seed import DEMO_USER_ID, seed_demo_database  # noqa: E402
from finn_api.db.engine import SessionLocal, engine  # noqa: E402
from finn_api.db.models import User  # noqa: E402


def ensure_demo_auth_subject_available(session: Session, auth_subject: UUID) -> None:
    conflicting_user = session.scalar(
        select(User).where(
            User.auth_subject == auth_subject,
            User.id != DEMO_USER_ID,
        )
    )
    if conflicting_user is not None:
        raise ValueError(
            "The supplied auth subject is already associated with another FINN user."
        )


def bind_demo_user(session: Session, auth_subject: UUID) -> None:
    ensure_demo_auth_subject_available(session, auth_subject)
    demo_user = session.get(User, DEMO_USER_ID)
    if demo_user is None:
        raise RuntimeError("The demo seed did not create its expected user.")
    demo_user.auth_subject = auth_subject


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotently load synthetic FINN evaluation data and bind its demo "
            "user to an existing identity-provider subject."
        )
    )
    parser.add_argument(
        "--auth-subject",
        required=True,
        type=UUID,
        help="UUID subject of the already-created evaluation user.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        try:
            ensure_demo_auth_subject_available(session, args.auth_subject)
        except ValueError as error:
            parser.error(str(error))
        counts = seed_demo_database(
            session,
            get_settings().data_directory,
        )
        bind_demo_user(session, args.auth_subject)
        session.commit()

    print("Synthetic FINN evaluation data is seeded.")
    for key, value in counts.items():
        print(f"{key}: {value}")
    engine.dispose()


if __name__ == "__main__":
    main()
