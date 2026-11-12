"""Store sector provenance on synthetic or authorized experience records.

Revision ID: 0003_experience_sector
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_experience_sector"
down_revision = "0002_market_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("person_experiences")
    }
    if "sector" not in columns:
        op.add_column(
            "person_experiences",
            sa.Column("sector", sa.String(length=120), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("person_experiences", "sector")
