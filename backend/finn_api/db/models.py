from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from finn_api.db.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    auth_subject: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    legal_name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    __table_args__ = (UniqueConstraint("exchange", "normalized_symbol"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(240))
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioCompany(Base):
    __tablename__ = "portfolio_companies"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "company_id"),
        Index("ix_portfolio_companies_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketDaily(Base):
    __tablename__ = "market_daily"
    __table_args__ = (
        UniqueConstraint("company_id", "exchange", "market_date", "source"),
        Index("ix_market_daily_company_date", "company_id", "market_date"),
        CheckConstraint("volume >= 0", name="ck_market_daily_volume_nonnegative"),
        CheckConstraint("close > 0", name="ck_market_daily_close_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    market_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_change: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    daily_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    average_volume_20: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    historical_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    adjusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("source", "source_key"),
        Index("ix_announcements_company_filed", "company_id", "filed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(240), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="unclassified", nullable=False)
    category_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    materiality: Mapped[str] = mapped_column(String(20), default="routine", nullable=False)
    materiality_score: Mapped[int | None] = mapped_column(Integer)
    materiality_reasons: Mapped[list[str] | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("announcement_categories.id", ondelete="SET NULL")
    )
    source_payload_hash: Mapped[str | None] = mapped_column(String(128))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieval_status: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False)
    raw_document_path: Mapped[str | None] = mapped_column(Text)
    source_payload: Mapped[dict | None] = mapped_column(JSON)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("company_id", "source_url", "content_hash"),
        Index("ix_documents_company_type_period", "company_id", "document_type", "period_end"),
        Index(
            "ix_documents_primary_period",
            "company_id",
            "is_primary_source",
            "document_type",
            "period_end",
        ),
        Index(
            "uq_documents_company_content_hash",
            "company_id",
            "content_hash",
            unique=True,
            postgresql_where=text(
                "ingestion_status IN ('extracted', 'embedded', 'downloaded')"
            ),
            sqlite_where=text(
                "ingestion_status IN ('extracted', 'embedded', 'downloaded')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    period_label: Mapped[str | None] = mapped_column(String(40))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reporting_basis: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(12))
    content_type: Mapped[str | None] = mapped_column(String(120))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_method: Mapped[str | None] = mapped_column(String(32))
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    ingestion_status: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", "content_hash"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(240))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        Index(
            "ix_financial_periods_company_metric",
            "company_id",
            "metric_key",
            "period_end",
            "reporting_basis",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    fiscal_year: Mapped[str] = mapped_column(String(16), nullable=False)
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reporting_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_scale: Mapped[str] = mapped_column(String(24), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(40), nullable=False)
    reported_value: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class NetworkPerson(Base):
    __tablename__ = "network_people"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    source_url: Mapped[str | None] = mapped_column(Text)
    consent_status: Mapped[str] = mapped_column(String(24), default="synthetic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PersonExperience(Base):
    __tablename__ = "person_experiences"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    experience_type: Mapped[str] = mapped_column(String(24), nullable=False)
    organization: Mapped[str] = mapped_column(String(240), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    sector: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    education_institution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("educational_institutions.id", ondelete="SET NULL")
    )
    data_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class NetworkEdge(Base):
    __tablename__ = "network_edges"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "from_person_id",
            "to_person_id",
            "edge_type",
            name="uq_network_edge_pair_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    from_person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    to_person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    relationship_strength: Mapped[str | None] = mapped_column(String(24))
    evidence: Mapped[str | None] = mapped_column(Text)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    portfolio_id: Mapped[UUID | None] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(40))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("announcement_categories.id", ondelete="SET NULL")
    )
    price_pct_threshold: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    volume_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    volume_lookback_days: Mapped[int | None] = mapped_column(Integer)
    priority_threshold: Mapped[int | None] = mapped_column(Integer)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "requested_ticker",
            "prompt_version",
            name="uq_research_run_workspace_ticker_prompt",
        ),
        Index("ix_research_runs_workspace_requested", "workspace_id", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    requested_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_route: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    source_manifest: Mapped[dict | None] = mapped_column(JSON)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ResearchCitation(Base):
    __tablename__ = "research_citations"
    __table_args__ = (
        UniqueConstraint(
            "research_run_id",
            "chunk_id",
            "claim_key",
            name="uq_research_citation_run_chunk_claim",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    research_run_id: Mapped[UUID] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"))
    claim_key: Mapped[str] = mapped_column(String(120), nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class NetworkMatch(Base):
    __tablename__ = "network_matches"
    __table_args__ = (
        CheckConstraint(
            "(announcement_id IS NOT NULL AND research_run_id IS NULL) OR "
            "(announcement_id IS NULL AND research_run_id IS NOT NULL)",
            name="ck_network_matches_one_context",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    announcement_id: Mapped[UUID | None] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"))
    research_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"))
    person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    match_type: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 5))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_status_available", "status", "available_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_key: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(120))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceSyncState(Base):
    __tablename__ = "source_sync_state"
    __table_args__ = (UniqueConstraint("source", "scope_key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(240), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class AnnouncementCategory(Base):
    __tablename__ = "announcement_categories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    category_key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key", name="uq_alert_workspace_dedupe"),
        Index("ix_alerts_workspace_status_created", "workspace_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    announcement_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL")
    )
    alert_rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL")
    )
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="unread", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(240), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FinancialMetric(Base):
    __tablename__ = "financial_metrics"
    __table_args__ = (
        UniqueConstraint(
            "statement_period_id",
            "metric_key",
            "reporting_basis",
            name="uq_financial_metric_period_key_basis",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_financial_metric_confidence_range",
        ),
        Index("ix_financial_metrics_key_period", "metric_key", "statement_period_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    statement_period_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_statement_periods.id", ondelete="CASCADE")
    )
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    metric_key: Mapped[str] = mapped_column(String(40), nullable=False)
    reported_value: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    unit_scale: Mapped[str] = mapped_column(String(24), nullable=False, default="unit")
    reporting_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialStatementPeriod(Base):
    __tablename__ = "financial_statement_periods"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "document_id",
            "period_label",
            "reporting_basis",
            name="uq_financial_statement_period",
        ),
        CheckConstraint("period_end >= period_start", name="ck_financial_statement_dates"),
        Index(
            "ix_financial_statement_company_end_basis",
            "company_id",
            "period_end",
            "reporting_basis",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    fiscal_year: Mapped[str] = mapped_column(String(16), nullable=False)
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reporting_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_scale: Mapped[str] = mapped_column(String(24), nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        UniqueConstraint("workspace_id", "report_key", name="uq_research_report_workspace_key"),
        Index("ix_research_reports_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    research_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL")
    )
    report_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict | None] = mapped_column(JSON)
    source_manifest: Mapped[dict | None] = mapped_column(JSON)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    model_route: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CopilotConversation(Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = (
        Index(
            "ix_copilot_conversations_user_workspace_updated",
            "user_id",
            "workspace_id",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    __table_args__ = (
        Index("ix_copilot_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("copilot_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    organization_type: Mapped[str] = mapped_column(String(32), default="employer", nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), unique=True
    )
    sector: Mapped[str | None] = mapped_column(String(120))
    website_url: Mapped[str | None] = mapped_column(Text)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EducationalInstitution(Base):
    __tablename__ = "educational_institutions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    institution_type: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(160))
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PersonEmployment(Base):
    __tablename__ = "person_employment_history"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "person_id",
            "organization_id",
            "title",
            "start_date",
            name="uq_person_employment_record",
        ),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_person_employment_dates",
        ),
        Index("ix_employment_person_dates", "person_id", "start_date"),
        Index("ix_employment_organization", "organization_id", "start_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PersonEducation(Base):
    __tablename__ = "person_education_history"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "person_id",
            "educational_institution_id",
            "start_date",
            name="uq_person_education_record",
        ),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_person_education_dates",
        ),
        Index("ix_education_person_dates", "person_id", "start_date"),
        Index("ix_education_institution", "educational_institution_id", "start_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    educational_institution_id: Mapped[UUID] = mapped_column(
        ForeignKey("educational_institutions.id", ondelete="RESTRICT")
    )
    qualification: Mapped[str | None] = mapped_column(String(160))
    field_of_study: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NetworkRelationship(Base):
    __tablename__ = "network_relationships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "from_person_id",
            "to_person_id",
            "relationship_type",
            name="uq_network_relationship_pair_type",
        ),
        CheckConstraint("from_person_id <> to_person_id", name="ck_network_relationship_not_self"),
        Index("ix_network_relationships_from", "workspace_id", "from_person_id"),
        Index("ix_network_relationships_to", "workspace_id", "to_person_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    from_person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    to_person_id: Mapped[UUID] = mapped_column(ForeignKey("network_people.id", ondelete="CASCADE"))
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(24))
    evidence: Mapped[str | None] = mapped_column(Text)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EntityMatch(Base):
    __tablename__ = "entity_matches"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_entity_match_confidence_range",
        ),
        CheckConstraint(
            "(company_id IS NOT NULL AND person_id IS NULL AND organization_id IS NULL "
            "AND educational_institution_id IS NULL) OR "
            "(company_id IS NULL AND person_id IS NOT NULL AND organization_id IS NULL "
            "AND educational_institution_id IS NULL) OR "
            "(company_id IS NULL AND person_id IS NULL AND organization_id IS NOT NULL "
            "AND educational_institution_id IS NULL) OR "
            "(company_id IS NULL AND person_id IS NULL AND organization_id IS NULL "
            "AND educational_institution_id IS NOT NULL)",
            name="ck_entity_match_single_candidate",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_id",
            "source_entity_key",
            "candidate_key",
            name="uq_entity_match_candidate",
        ),
        Index("ix_entity_matches_source_key", "source_id", "source_entity_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE")
    )
    source_entity_key: Mapped[str] = mapped_column(String(240), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(280), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("network_people.id", ondelete="CASCADE")
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    educational_institution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("educational_institutions.id", ondelete="CASCADE")
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ManagementGuidance(Base):
    __tablename__ = "management_guidance"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "guidance_key",
            name="uq_management_guidance_company_key",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_management_guidance_confidence_range",
        ),
        Index("ix_guidance_company_period", "company_id", "period_end"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    guidance_key: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(40), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    target_low: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    target_high: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    currency: Mapped[str | None] = mapped_column(String(3))
    unit_scale: Mapped[str | None] = mapped_column(String(24))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuidanceAssessment(Base):
    __tablename__ = "guidance_assessments"
    __table_args__ = (
        UniqueConstraint(
            "guidance_id",
            "assessment_document_id",
            name="uq_guidance_assessment_document",
        ),
        Index("ix_guidance_assessment_guidance", "guidance_id", "assessed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    guidance_id: Mapped[UUID] = mapped_column(
        ForeignKey("management_guidance.id", ondelete="CASCADE")
    )
    assessment_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    financial_metric_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("financial_metrics.id", ondelete="SET NULL")
    )
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    rationale: Mapped[str | None] = mapped_column(Text)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
