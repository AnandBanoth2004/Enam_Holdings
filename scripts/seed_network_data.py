"""
seed_network_data.py – Load the synthetic network fixture into a workspace.

Usage:
    python scripts/seed_network_data.py --workspace-id <uuid>

This script is idempotent; running it multiple times against the same workspace
is safe. All seeded profiles are explicitly marked synthetic=True.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.engine import engine
from finn_api.db.models import Base, DataSource, Workspace
from finn_api.data_pipeline.network_seed import (
    load_synthetic_contact_dataset,
    seed_synthetic_contacts,
)

FIXTURE_PATH = ROOT / "data" / "fixtures" / "network_contacts.json"


def _ensure_data_source(session: Session, synthetic: bool) -> None:
    existing = session.scalar(
        select(DataSource).where(DataSource.source_key == "synthetic_network_fixture")
    )
    if existing is None:
        session.add(
            DataSource(
                source_key="synthetic_network_fixture",
                display_name="FINN Synthetic Network Fixture",
                source_type="synthetic",
                is_primary=False,
                is_synthetic=synthetic,
            )
        )
        session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FINN synthetic network contacts.")
    parser.add_argument(
        "--workspace-id",
        required=True,
        type=UUID,
        help="UUID of the target workspace.",
    )
    args = parser.parse_args()
    workspace_id: UUID = args.workspace_id

    dataset = load_synthetic_contact_dataset(FIXTURE_PATH)
    print(f"[network-seed] Loaded dataset '{dataset.dataset_id}' with {len(dataset.profiles)} profiles.")
    print(f"[network-seed] Notice: {dataset.notice}")

    with Session(engine) as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            print(f"[network-seed] ERROR: workspace {workspace_id} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"[network-seed] Target workspace: '{workspace.name}' (synthetic={workspace.synthetic})")
        _ensure_data_source(session, synthetic=workspace.synthetic)
        inserted = seed_synthetic_contacts(session, workspace_id=workspace_id, dataset=dataset)
        print(f"[network-seed] Inserted {inserted} new contact(s). (0 means already seeded.)")
        session.commit()

    print("[network-seed] Done.")


if __name__ == "__main__":
    main()
