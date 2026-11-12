"""Store the last evidenced network interaction.

Revision ID: 0007_network_relationship_interaction
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_network_relationship_interaction"
down_revision = "0006_pull_document_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("network_relationships")
    }
    if "last_interaction_at" not in columns:
        op.add_column(
            "network_relationships",
            sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    columns = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns("network_relationships")
    }
    if "last_interaction_at" in columns:
        op.drop_column("network_relationships", "last_interaction_at")
