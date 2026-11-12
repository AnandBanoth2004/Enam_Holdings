"""Store workspace- and user-scoped Copilot conversations.

Revision ID: 0008_copilot_conversations
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_copilot_conversations"
down_revision = "0007_network_relationship_interaction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_conversations_user_workspace_updated",
        "copilot_conversations",
        ["user_id", "workspace_id", "updated_at"],
    )
    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["copilot_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_messages_conversation_created",
        "copilot_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_messages_conversation_created", table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_index(
        "ix_copilot_conversations_user_workspace_updated",
        table_name="copilot_conversations",
    )
    op.drop_table("copilot_conversations")
