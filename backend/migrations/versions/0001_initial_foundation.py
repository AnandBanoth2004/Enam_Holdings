"""Create the initial FINN relational foundation.

Revision ID: 0001_initial
"""
from alembic import op
from sqlalchemy import MetaData

from finn_api.db.base import Base
from finn_api.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    legacy_metadata = MetaData()
    migration_columns = {
        "market_daily": {
            "open",
            "high",
            "low",
            "adjusted_close",
            "daily_change",
            "daily_change_pct",
            "average_volume_20",
            "volume_ratio",
        },
        "announcements": {
            "source_timestamp",
            "retrieval_status",
            "raw_document_path",
            "source_payload",
        },
        "person_experiences": {"sector"},
    }
    for table in Base.metadata.sorted_tables:
        legacy_table = table.to_metadata(legacy_metadata)
        for column_name in migration_columns.get(table.name, set()):
            if column_name in legacy_table.c:
                legacy_table._columns.remove(legacy_table.c[column_name])
    legacy_metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
