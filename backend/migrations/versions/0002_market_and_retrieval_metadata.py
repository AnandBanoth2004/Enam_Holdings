"""Add EOD OHLC metrics and source retrieval metadata.

Revision ID: 0002_market_retrieval
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_market_retrieval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    market_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("market_daily")
    }
    for column in (
        sa.Column("open", sa.Numeric(20, 6), nullable=True),
        sa.Column("high", sa.Numeric(20, 6), nullable=True),
        sa.Column("low", sa.Numeric(20, 6), nullable=True),
        sa.Column("adjusted_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("daily_change", sa.Numeric(20, 6), nullable=True),
        sa.Column("daily_change_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("average_volume_20", sa.Numeric(24, 6), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(16, 6), nullable=True),
    ):
        if column.name not in market_columns:
            op.add_column("market_daily", column)

    announcement_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("announcements")
    }
    if "source_timestamp" not in announcement_columns:
        op.add_column("announcements", sa.Column("source_timestamp", sa.DateTime(timezone=True)))
    if "retrieval_status" not in announcement_columns:
        op.add_column(
            "announcements",
            sa.Column(
                "retrieval_status",
                sa.String(length=24),
                nullable=False,
                server_default="discovered",
            ),
        )
        op.alter_column("announcements", "retrieval_status", server_default=None)
    if "raw_document_path" not in announcement_columns:
        op.add_column("announcements", sa.Column("raw_document_path", sa.Text()))
    if "source_payload" not in announcement_columns:
        op.add_column("announcements", sa.Column("source_payload", sa.JSON()))


def downgrade() -> None:
    op.drop_column("announcements", "source_payload")
    op.drop_column("announcements", "raw_document_path")
    op.drop_column("announcements", "retrieval_status")
    op.drop_column("announcements", "source_timestamp")
    for column in (
        "volume_ratio",
        "average_volume_20",
        "daily_change_pct",
        "daily_change",
        "adjusted_close",
        "low",
        "high",
        "open",
    ):
        op.drop_column("market_daily", column)
