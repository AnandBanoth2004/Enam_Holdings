"""Persist Push classification summaries and materiality explanations.

Revision ID: 0005_push_intelligence
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_push_intelligence"
down_revision = "0004_complete_model"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("announcements", sa.Column("summary", sa.Text(), nullable=True))
    _add_column_if_missing(
        "announcements", sa.Column("materiality_score", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        "announcements", sa.Column("materiality_reasons", sa.JSON(), nullable=True)
    )
    _add_column_if_missing(
        "alert_rules", sa.Column("priority_threshold", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("alert_rules")}
    if "priority_threshold" in columns:
        op.drop_column("alert_rules", "priority_threshold")
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("announcements")}
    for column in ("materiality_reasons", "materiality_score", "summary"):
        if column in columns:
            op.drop_column("announcements", column)
