"""Add document ingestion and primary-source metadata.

Revision ID: 0006_pull_document_processing
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_pull_document_processing"
down_revision = "0005_push_intelligence"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("period_label", sa.String(length=40), nullable=True),
    sa.Column("content_type", sa.String(length=120), nullable=True),
    sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    sa.Column("storage_path", sa.Text(), nullable=True),
    sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("extraction_method", sa.String(length=32), nullable=True),
    sa.Column(
        "is_primary_source",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
)


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("documents")}
    for column in _COLUMNS:
        if column.name not in columns:
            op.add_column("documents", column)

    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("documents")}
    if "ix_documents_primary_period" not in indexes:
        op.create_index(
            "ix_documents_primary_period",
            "documents",
            ["company_id", "is_primary_source", "document_type", "period_end"],
        )
    if "uq_documents_company_content_hash" not in indexes:
        op.create_index(
            "uq_documents_company_content_hash",
            "documents",
            ["company_id", "content_hash"],
            unique=True,
            postgresql_where=sa.text(
                "ingestion_status IN ('extracted', 'embedded', 'downloaded')"
            ),
            sqlite_where=sa.text(
                "ingestion_status IN ('extracted', 'embedded', 'downloaded')"
            ),
        )


def downgrade() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("documents")}
    if "uq_documents_company_content_hash" in indexes:
        op.drop_index("uq_documents_company_content_hash", table_name="documents")
    if "ix_documents_primary_period" in indexes:
        op.drop_index("ix_documents_primary_period", table_name="documents")
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("documents")}
    for column in reversed(_COLUMNS):
        if column.name in columns:
            op.drop_column("documents", column.name)
