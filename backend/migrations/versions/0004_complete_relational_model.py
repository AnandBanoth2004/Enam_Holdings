"""Complete FINN relational model and provenance flags.

Revision ID: 0004_complete_model
"""
from alembic import op
import sqlalchemy as sa

from finn_api.db.base import Base
from finn_api.db import models  # noqa: F401

revision = "0004_complete_model"
down_revision = "0003_experience_sector"
branch_labels = None
depends_on = None


_COLUMNS = {
    "workspaces": {
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "companies": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "company_aliases": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "portfolios": {
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "portfolio_companies": {
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "market_daily": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "announcements": {
        "category_id": sa.Column("category_id", sa.Uuid()),
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "documents": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        "created_at": sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    },
    "document_chunks": {
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "financial_periods": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "network_people": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
    },
    "person_experiences": {
        "organization_id": sa.Column("organization_id", sa.Uuid()),
        "education_institution_id": sa.Column("education_institution_id", sa.Uuid()),
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "network_edges": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
        "synthetic": sa.Column(
            "synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "alert_rules": {
        "category_id": sa.Column("category_id", sa.Uuid()),
        "is_synthetic": sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "research_runs": {
        "is_synthetic": sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
    },
    "research_reports": {
        "data_source_id": sa.Column("data_source_id", sa.Uuid()),
    },
    "research_citations": {
        "is_synthetic": sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "network_matches": {
        "is_synthetic": sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
    "ingestion_jobs": {
        "is_synthetic": sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    },
}

_FOREIGN_KEYS = {
    "companies": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "company_aliases": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "market_daily": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "announcements": {
        "category_id": ("announcement_categories", "id", "SET NULL"),
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "documents": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "financial_periods": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "network_people": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "person_experiences": {
        "organization_id": ("organizations", "id", "SET NULL"),
        "education_institution_id": ("educational_institutions", "id", "SET NULL"),
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "alert_rules": {
        "category_id": ("announcement_categories", "id", "SET NULL"),
    },
    "network_edges": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "research_runs": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "research_reports": {
        "data_source_id": ("data_sources", "id", "SET NULL"),
    },
    "workspace_members": {
        "user_id": ("users", "id", "CASCADE"),
    },
}
_NEW_TABLES = {
    "users",
    "announcement_categories",
    "alerts",
    "financial_metrics",
    "financial_statement_periods",
    "research_reports",
    "organizations",
    "educational_institutions",
    "person_employment_history",
    "person_education_history",
    "network_relationships",
    "entity_matches",
    "data_sources",
    "management_guidance",
    "guidance_assessments",
    "audit_logs",
}
_UNIQUE_CONSTRAINTS = {
    "network_edges": (
        (
            "uq_network_edge_pair_type",
            ["workspace_id", "from_person_id", "to_person_id", "edge_type"],
        ),
    ),
    "person_employment_history": (
        (
            "uq_person_employment_record",
            ["workspace_id", "person_id", "organization_id", "title", "start_date"],
        ),
    ),
    "person_education_history": (
        (
            "uq_person_education_record",
            ["workspace_id", "person_id", "educational_institution_id", "start_date"],
        ),
    ),
    "research_runs": (
        (
            "uq_research_run_workspace_ticker_prompt",
            ["workspace_id", "requested_ticker", "prompt_version"],
        ),
    ),
    "research_citations": (
        (
            "uq_research_citation_run_chunk_claim",
            ["research_run_id", "chunk_id", "claim_key"],
        ),
    ),
}


def _add_missing_columns() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, columns in _COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column in columns.items():
            if column_name not in existing:
                op.add_column(table_name, column)
                if column.server_default is not None and column_name != "created_at":
                    op.alter_column(table_name, column_name, server_default=None)


def _backfill_application_users() -> None:
    connection = op.get_bind()
    members = connection.execute(
        sa.text("SELECT DISTINCT user_id FROM workspace_members WHERE user_id IS NOT NULL")
    ).fetchall()
    for member in members:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, auth_subject, synthetic, created_at, updated_at) "
                "VALUES (:user_id, :user_id, FALSE, now(), now()) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"user_id": member.user_id},
        )


def _add_missing_foreign_keys() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, foreign_keys in _FOREIGN_KEYS.items():
        existing = {
            (column, foreign_key["referred_table"])
            for foreign_key in inspector.get_foreign_keys(table_name)
            for column in foreign_key["constrained_columns"]
        }
        for column, (referred_table, referred_column, ondelete) in foreign_keys.items():
            if (column, referred_table) not in existing:
                op.create_foreign_key(
                    f"fk_{table_name}_{column}_{referred_table}",
                    table_name,
                    referred_table,
                    [column],
                    [referred_column],
                    ondelete=ondelete,
                )


def _add_missing_unique_constraints() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, constraints in _UNIQUE_CONSTRAINTS.items():
        existing = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table_name)
        }
        for constraint_name, columns in constraints:
            if tuple(columns) not in existing:
                op.create_unique_constraint(constraint_name, table_name, columns)


def upgrade() -> None:
    _add_missing_columns()
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    _backfill_application_users()
    _add_missing_foreign_keys()
    _add_missing_unique_constraints()


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, constraints in _UNIQUE_CONSTRAINTS.items():
        existing = {
            tuple(constraint["column_names"]): constraint["name"]
            for constraint in inspector.get_unique_constraints(table_name)
        }
        for constraint_name, columns in constraints:
            name = existing.get(tuple(columns))
            if name:
                op.drop_constraint(name, table_name, type_="unique")

    inspector = sa.inspect(op.get_bind())
    for table_name, foreign_keys in _FOREIGN_KEYS.items():
        existing = {
            (column, foreign_key["referred_table"], foreign_key["name"])
            for foreign_key in inspector.get_foreign_keys(table_name)
            for column in foreign_key["constrained_columns"]
        }
        for column, (referred_table, _, _) in foreign_keys.items():
            matches = [
                name
                for constrained_column, referenced_table, name in existing
                if constrained_column == column and referenced_table == referred_table
            ]
            for name in matches:
                if name:
                    op.drop_constraint(name, table_name, type_="foreignkey")

    for table in reversed(Base.metadata.sorted_tables):
        if table.name in _NEW_TABLES:
            op.drop_table(table.name)

    for table_name, columns in reversed(tuple(_COLUMNS.items())):
        existing_columns = {
            column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
        }
        for column_name in reversed(tuple(columns)):
            if column_name in existing_columns:
                op.drop_column(table_name, column_name)
