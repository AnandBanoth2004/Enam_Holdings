from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.network_seed import (
    load_synthetic_contact_dataset,
    seed_synthetic_contacts,
)
from finn_api.db.models import (
    Alert,
    AlertRule,
    Announcement,
    AnnouncementCategory,
    AuditLog,
    Company,
    CompanyAlias,
    DataSource,
    Document,
    DocumentChunk,
    EntityMatch,
    FinancialMetric,
    FinancialStatementPeriod,
    GuidanceAssessment,
    ManagementGuidance,
    MarketDaily,
    NetworkPerson,
    Portfolio,
    PortfolioCompany,
    ResearchCitation,
    ResearchReport,
    ResearchRun,
    SourceSyncState,
    User,
    Workspace,
    WorkspaceMember,
)
from finn_api.db.seed import load_seed_file
from finn_api.push.service import classify_pending_announcements


DEMO_WORKSPACE_ID = UUID("3c39b2f3-b3f3-4f34-9b20-5fd985e64301")
DEMO_USER_ID = UUID("84968d61-5fdc-4c12-8d15-71e67b522e8f")
DEMO_PORTFOLIO_ID = UUID("6de7c69a-8337-4aeb-aac3-e5e2a60494c8")
MARKET_DATES = tuple(
    date(2026, 11, day) for day in (4, 5, 6, 9, 10)
)
EXCHANGE_TZ = ZoneInfo("Asia/Kolkata")

SOURCE_DEFINITIONS = (
    ("nse_public_announcements", "NSE public announcements", "exchange", "https://www.nseindia.com/api/corporate-announcements", True, False),
    ("bse_public_announcements", "BSE public announcements", "exchange", "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w", True, False),
    ("yfinance", "Yahoo Finance daily history adapter", "market_data", "https://finance.yahoo.com/", False, False),
    ("issuer_ir", "Issuer investor-relations websites", "issuer_primary", None, True, False),
    ("company_seed", "Curated FINN demo issuer mapping", "seed", None, False, True),
    ("synthetic_demo", "FINN synthetic demonstration fixtures", "synthetic_fixture", None, False, True),
    ("synthetic_network_fixture", "FINN fictional network fixture", "synthetic_fixture", None, False, True),
)

CATEGORY_FIXTURE = "fixtures/announcement_categories.json"
ANNOUNCEMENT_FIXTURE = "fixtures/demo_announcements.json"
NETWORK_FIXTURE = "fixtures/network_contacts.json"
COMPANY_FIXTURE = "seed/demo_seed.json"

DOCUMENT_FIXTURES = (
    ("RELIANCE", "quarterly_result", "Q2 FY26 synthetic result example", "fixtures/documents/reliance_q2_example.txt"),
    ("TCS", "quarterly_result", "Q2 FY26 synthetic result example", "fixtures/documents/tcs_q2_example.txt"),
    ("HDFCBANK", "quarterly_result", "Q2 FY26 synthetic result example", "fixtures/documents/hdfc_q2_example.txt"),
    ("SUNPHARMA", "quarterly_result", "Q2 FY26 synthetic result example", "fixtures/documents/sunpharma_q2_example.txt"),
    ("RELIANCE", "annual_report", "Synthetic annual report structure example", "fixtures/documents/annual_report_example.txt"),
    ("TCS", "earnings_call_transcript", "Synthetic earnings call transcript structure example", "fixtures/documents/transcript_example.txt"),
    ("HDFCBANK", "investor_presentation", "Synthetic investor presentation structure example", "fixtures/documents/presentation_example.txt"),
)

SYNTHETIC_FINANCIALS: dict[str, dict[str, Decimal]] = {
    "RELIANCE": {"revenue": Decimal("1000"), "ebitda": Decimal("180"), "pbt": Decimal("140"), "pat": Decimal("100")},
    "TCS": {"revenue": Decimal("800"), "ebitda": Decimal("190"), "pbt": Decimal("175"), "pat": Decimal("130")},
    "HDFCBANK": {"revenue": Decimal("700"), "ebitda": Decimal("210"), "pbt": Decimal("160"), "pat": Decimal("120")},
    "SUNPHARMA": {"revenue": Decimal("600"), "ebitda": Decimal("150"), "pbt": Decimal("125"), "pat": Decimal("90")},
}


def _get_or_create_sources(session: Session) -> dict[str, DataSource]:
    sources: dict[str, DataSource] = {}
    for key, name, source_type, url, primary, synthetic in SOURCE_DEFINITIONS:
        source = session.scalar(select(DataSource).where(DataSource.source_key == key))
        if source is None:
            source = DataSource(
                source_key=key,
                display_name=name,
                source_type=source_type,
                base_url=url,
                is_primary=primary,
                is_synthetic=synthetic,
            )
            session.add(source)
            session.flush()
        sources[key] = source
    return sources


def _get_or_create_workspace(session: Session) -> tuple[Workspace, User]:
    workspace = session.get(Workspace, DEMO_WORKSPACE_ID)
    if workspace is None:
        workspace = Workspace(
            id=DEMO_WORKSPACE_ID,
            name="FINN Synthetic Demo Workspace",
            synthetic=True,
        )
        session.add(workspace)

    user = session.get(User, DEMO_USER_ID)
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            auth_subject=DEMO_USER_ID,
            email="demo.user@finn.example",
            display_name="FINN Demo User",
            synthetic=True,
        )
        session.add(user)
    session.flush()

    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership is None:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
        )
    return workspace, user


def _seed_categories(session: Session, fixture_path: Path) -> dict[str, AnnouncementCategory]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    categories: dict[str, AnnouncementCategory] = {}
    for row in payload["categories"]:
        category = session.scalar(
            select(AnnouncementCategory).where(
                AnnouncementCategory.category_key == row["category_key"]
            )
        )
        if category is None:
            category = AnnouncementCategory(
                category_key=row["category_key"],
                display_name=row["display_name"],
                priority=row["priority"],
                synthetic=False,
            )
            session.add(category)
            session.flush()
        categories[category.category_key] = category
    return categories


def _company_maps(session: Session) -> tuple[dict[str, Company], dict[str, CompanyAlias]]:
    aliases = session.scalars(select(CompanyAlias)).all()
    companies = session.scalars(select(Company)).all()
    companies_by_id = {company.id: company for company in companies}
    return (
        {alias.normalized_symbol: companies_by_id[alias.company_id] for alias in aliases},
        {alias.normalized_symbol: alias for alias in aliases},
    )


def _seed_portfolio(
    session: Session,
    workspace: Workspace,
    seed_path: Path,
    companies: dict[str, Company],
) -> Portfolio:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    portfolio = session.get(Portfolio, DEMO_PORTFOLIO_ID)
    if portfolio is None:
        portfolio = Portfolio(
            id=DEMO_PORTFOLIO_ID,
            workspace_id=workspace.id,
            name="FINN 18-company demo portfolio",
            is_default=True,
            synthetic=True,
        )
        session.add(portfolio)
        session.flush()
    for order, row in enumerate(seed["companies"]):
        symbol = row["symbol"].upper().removesuffix(".NS")
        company = companies[symbol]
        link = session.scalar(
            select(PortfolioCompany).where(
                PortfolioCompany.portfolio_id == portfolio.id,
                PortfolioCompany.company_id == company.id,
            )
        )
        if link is None:
            session.add(
                PortfolioCompany(
                    portfolio_id=portfolio.id,
                    company_id=company.id,
                    display_order=order,
                    synthetic=True,
                )
            )
    return portfolio


def _seed_market_prices(
    session: Session,
    companies: dict[str, Company],
    aliases: dict[str, CompanyAlias],
    source_id: UUID,
    fetched_at: datetime,
) -> int:
    inserted = 0
    for company_index, (ticker, company) in enumerate(sorted(companies.items())):
        if ticker not in aliases or ticker not in {
            "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "LT",
            "SBIN", "BHARTIARTL", "AXISBANK", "KOTAKBANK", "HINDUNILVR",
            "BAJFINANCE", "MARUTI", "SUNPHARMA", "TATAMOTORS", "TITAN",
            "ASIANPAINT", "POWERGRID", "M&M", "WIPRO", "CIPLA",
        }:
            continue
        base_close = Decimal(120 + company_index * 37)
        for day_index, market_date in enumerate(MARKET_DATES):
            close = base_close + Decimal(day_index * (company_index % 4 + 1))
            key = select(MarketDaily).where(
                MarketDaily.company_id == company.id,
                MarketDaily.exchange == "NSE",
                MarketDaily.market_date == market_date,
                MarketDaily.source == "synthetic_demo",
            )
            row = session.scalar(key)
            previous_close = close - Decimal(company_index % 4 + 1)
            daily_change = Decimal(0) if day_index == 0 else close - previous_close
            volume = 100_000 + company_index * 5_000 + day_index * 1_500
            values = {
                "open": close - Decimal("0.5"),
                "high": close + Decimal("1.2"),
                "low": close - Decimal("1.1"),
                "close": close,
                "adjusted_close": close,
                "volume": volume,
                "daily_change": daily_change,
                "daily_change_pct": daily_change / previous_close * Decimal(100)
                if day_index
                else Decimal(0),
                "currency": "INR",
                "adjusted": True,
                "data_source_id": source_id,
                "synthetic": True,
                "fetched_at": fetched_at,
            }
            if row is None:
                session.add(
                    MarketDaily(
                        company_id=company.id,
                        exchange="NSE",
                        market_date=market_date,
                        source="synthetic_demo",
                        **values,
                    )
                )
                inserted += 1
            else:
                for field, value in values.items():
                    setattr(row, field, value)
    return inserted


def _seed_announcements(
    session: Session,
    fixture_path: Path,
    categories: dict[str, AnnouncementCategory],
    companies: dict[str, Company],
    source_id: UUID,
    fetched_at: datetime,
) -> int:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("synthetic") is not True:
        raise ValueError("Demo announcements fixture must be explicitly synthetic.")

    inserted = 0
    for row in payload["announcements"]:
        ticker = row["ticker"]
        company = companies[ticker]
        filed_at = datetime.combine(
            date(2026, 11, 10), time(9 + inserted % 7, (inserted * 7) % 60), EXCHANGE_TZ
        )
        existing = session.scalar(
            select(Announcement).where(
                Announcement.source == "demo_fixture",
                Announcement.source_key == row["source_key"],
            )
        )
        values = {
            "company_id": company.id,
            "source_url": f"fixture://announcements/{row['source_key']}",
            "headline": row["headline"],
            "body_text": row["body_text"],
            "filed_at": filed_at,
            "category_id": categories[row["category"]].id,
            "category": row["category"],
            "category_confidence": Decimal("1.0000"),
            "materiality": "illustrative",
            "source_payload_hash": hashlib.sha256(
                json.dumps(row, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "source_timestamp": filed_at,
            "retrieval_status": "demo_fixture",
            "source_payload": row,
            "data_source_id": source_id,
            "synthetic": True,
            "fetched_at": fetched_at,
        }
        if existing is None:
            session.add(
                Announcement(
                    source="demo_fixture",
                    source_key=row["source_key"],
                    **values,
                )
            )
            inserted += 1
        else:
            for field, value in values.items():
                setattr(existing, field, value)
    return inserted


def _seed_documents(
    session: Session,
    fixture_root: Path,
    companies: dict[str, Company],
    source_id: UUID,
    fetched_at: datetime,
) -> tuple[dict[tuple[str, str], Document], int]:
    documents: dict[tuple[str, str], Document] = {}
    inserted = 0
    for ticker, document_type, title, relative_path in DOCUMENT_FIXTURES:
        company = companies[ticker]
        path = fixture_root / relative_path
        content = path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        source_url = f"fixture://documents/{path.stem}"
        document = session.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_url == source_url,
                Document.content_hash == content_hash,
            )
        )
        if document is None:
            document = Document(
                company_id=company.id,
                document_type=document_type,
                title=f"[DEMO ONLY] {title}",
                source_url=source_url,
                source_name="FINN synthetic fixture (not issuer evidence)",
                period_start=date(2025, 7, 1) if document_type == "quarterly_result" else None,
                period_end=date(2025, 9, 30) if document_type == "quarterly_result" else None,
                published_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
                reporting_basis="illustrative",
                language="en",
                content_hash=content_hash,
                ingestion_status="demo_fixture",
                data_source_id=source_id,
                synthetic=True,
                fetched_at=fetched_at,
            )
            session.add(document)
            session.flush()
            inserted += 1
        documents[(ticker, document_type)] = document

        chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk = session.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.chunk_index == 0,
                DocumentChunk.content_hash == chunk_hash,
            )
        )
        if chunk is None:
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    page_start=1,
                    page_end=1,
                    section="Synthetic fixture disclaimer and example",
                    text=content,
                    token_count=len(content.split()),
                    content_hash=chunk_hash,
                    synthetic=True,
                )
            )
    return documents, inserted


def _seed_financial_records(
    session: Session,
    companies: dict[str, Company],
    documents: dict[tuple[str, str], Document],
    source_id: UUID,
    fetched_at: datetime,
) -> dict[tuple[str, str], FinancialMetric]:
    metrics_by_ticker: dict[tuple[str, str], FinancialMetric] = {}
    for ticker, observations in SYNTHETIC_FINANCIALS.items():
        company = companies[ticker]
        document = documents[(ticker, "quarterly_result")]
        period = session.scalar(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.company_id == company.id,
                FinancialStatementPeriod.document_id == document.id,
                FinancialStatementPeriod.period_label == "Q2 FY26",
                FinancialStatementPeriod.reporting_basis == "consolidated",
            )
        )
        if period is None:
            period = FinancialStatementPeriod(
                company_id=company.id,
                document_id=document.id,
                fiscal_year="FY26",
                period_label="Q2 FY26",
                period_start=date(2025, 7, 1),
                period_end=date(2025, 9, 30),
                period_type="quarter",
                reporting_basis="consolidated",
                currency="INR",
                unit_scale="crore",
                data_source_id=source_id,
                is_synthetic=True,
            )
            session.add(period)
            session.flush()

        for metric_key, value in observations.items():
            metric = session.scalar(
                select(FinancialMetric).where(
                    FinancialMetric.statement_period_id == period.id,
                    FinancialMetric.metric_key == metric_key,
                    FinancialMetric.reporting_basis == "consolidated",
                )
            )
            if metric is None:
                metric = FinancialMetric(
                    statement_period_id=period.id,
                    document_id=document.id,
                    metric_key=metric_key,
                    reported_value=value,
                    currency="INR",
                    unit_scale="crore",
                    reporting_basis="consolidated",
                    source_page=1,
                    source_excerpt=(
                        f"Synthetic fixture only; illustrative {metric_key}={value} INR crore. "
                        "Not an issuer-reported value."
                    ),
                    extraction_method="synthetic_fixture",
                    confidence=Decimal("1.0000"),
                    data_source_id=source_id,
                    is_synthetic=True,
                )
                session.add(metric)
                session.flush()
            else:
                metric.reported_value = value
                metric.source_excerpt = (
                    f"Synthetic fixture only; illustrative {metric_key}={value} INR crore. "
                    "Not an issuer-reported value."
                )
            metrics_by_ticker[(ticker, metric_key)] = metric

    return metrics_by_ticker


def _seed_guidance(
    session: Session,
    companies: dict[str, Company],
    documents: dict[tuple[str, str], Document],
    metrics: dict[tuple[str, str], FinancialMetric],
    source_id: UUID,
) -> int:
    inserted = 0
    for ticker, observations in SYNTHETIC_FINANCIALS.items():
        company = companies[ticker]
        document = documents[(ticker, "quarterly_result")]
        guidance = session.scalar(
            select(ManagementGuidance).where(
                ManagementGuidance.company_id == company.id,
                ManagementGuidance.guidance_key == "demo-fy26-revenue",
            )
        )
        if guidance is None:
            revenue = observations["revenue"]
            guidance = ManagementGuidance(
                company_id=company.id,
                document_id=document.id,
                data_source_id=source_id,
                guidance_key="demo-fy26-revenue",
                metric_key="revenue",
                statement=(
                    "Synthetic guidance fixture only: illustrative full-year revenue "
                    "range, not management guidance."
                ),
                period_start=date(2025, 4, 1),
                period_end=date(2026, 3, 31),
                target_low=revenue * Decimal("3.5"),
                target_high=revenue * Decimal("4.5"),
                currency="INR",
                unit_scale="crore",
                source_page=1,
                source_excerpt="Fabricated demo text; not an issuer statement.",
                confidence=Decimal("1.0000"),
                is_synthetic=True,
            )
            session.add(guidance)
            session.flush()
            inserted += 1
        metric = metrics[(ticker, "revenue")]
        assessment = session.scalar(
            select(GuidanceAssessment).where(
                GuidanceAssessment.guidance_id == guidance.id,
                GuidanceAssessment.assessment_document_id == document.id,
            )
        )
        if assessment is None:
            session.add(
                GuidanceAssessment(
                    guidance_id=guidance.id,
                    assessment_document_id=document.id,
                    financial_metric_id=metric.id,
                    outcome="illustrative",
                    expected_value=metric.reported_value,
                    actual_value=metric.reported_value,
                    rationale="Synthetic demonstration assessment; not an evaluation of company guidance.",
                    source_excerpt="All values in this assessment are fabricated demo placeholders.",
                    is_synthetic=True,
                )
            )
    return inserted


def _seed_research_reports(
    session: Session,
    workspace: Workspace,
    companies: dict[str, Company],
    documents: dict[tuple[str, str], Document],
    source_id: UUID,
    fetched_at: datetime,
) -> int:
    inserted = 0
    for ticker in SYNTHETIC_FINANCIALS:
        company = companies[ticker]
        document = documents[(ticker, "quarterly_result")]
        report_key = f"demo-synthetic-{ticker.lower()}-q2fy26"
        report = session.scalar(
            select(ResearchReport).where(
                ResearchReport.workspace_id == workspace.id,
                ResearchReport.report_key == report_key,
            )
        )
        run = session.scalar(
            select(ResearchRun).where(
                ResearchRun.workspace_id == workspace.id,
                ResearchRun.requested_ticker == ticker,
                ResearchRun.prompt_version == "synthetic-fixture-v1",
                ResearchRun.is_synthetic.is_(True),
            )
        )
        if run is None:
            run = ResearchRun(
                workspace_id=workspace.id,
                requested_ticker=ticker,
                company_id=company.id,
                status="demo_fixture",
                requested_at=fetched_at,
                completed_at=fetched_at,
                model_route="none_synthetic_fixture",
                prompt_version="synthetic-fixture-v1",
                source_manifest={
                    "synthetic": True,
                    "warning": "Not research and not company-reported data.",
                    "document_ids": [str(document.id)],
                },
                data_source_id=source_id,
                result={"synthetic": True, "message": "Illustrative data only; no research generated."},
                is_synthetic=True,
            )
            session.add(run)
            session.flush()
        if report is None:
            report = ResearchReport(
                workspace_id=workspace.id,
                company_id=company.id,
                research_run_id=run.id,
                report_key=report_key,
                title=f"[DEMO ONLY] Synthetic model example for {ticker}",
                status="demo_fixture",
                summary="Synthetic fixture record; it contains no investment research or issuer facts.",
                content={
                    "synthetic": True,
                    "disclaimer": "This fabricated report is not company research.",
                    "ticker_mapping": ticker,
                },
                source_manifest={"synthetic": True, "fixture_document_id": str(document.id)},
                data_source_id=source_id,
                is_synthetic=True,
                created_at=fetched_at,
            )
            session.add(report)
            inserted += 1
        chunk = session.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.chunk_index == 0,
            )
        )
        if chunk is not None:
            citation = session.scalar(
                select(ResearchCitation).where(
                    ResearchCitation.research_run_id == run.id,
                    ResearchCitation.chunk_id == chunk.id,
                    ResearchCitation.claim_key == "synthetic_fixture_disclaimer",
                )
            )
            if citation is None:
                session.add(
                    ResearchCitation(
                        research_run_id=run.id,
                        chunk_id=chunk.id,
                        claim_key="synthetic_fixture_disclaimer",
                        page_start=1,
                        page_end=1,
                        quoted_text="NOT AN ISSUER FILING. NOT COMPANY-REPORTED DATA.",
                        source_url=document.source_url,
                        is_synthetic=True,
                    )
                )
    return inserted


def _seed_alerts(
    session: Session,
    workspace: Workspace,
    portfolio: Portfolio,
    company: Company,
    categories: dict[str, AnnouncementCategory],
    source_id: UUID,
) -> int:
    results_announcement = session.scalar(
        select(Announcement).where(
            Announcement.company_id == company.id,
            Announcement.source == "demo_fixture",
            Announcement.source_key == "demo-db-results-001",
        )
    )
    rule_defs = (
        ("synthetic-price-move", "price_move", None, Decimal("3.00"), None),
        ("synthetic-results-category", "announcement_category", "results", None, None),
    )
    rules: dict[str, AlertRule] = {}
    inserted = 0
    for key, rule_type, category_key, price_threshold, volume_multiplier in rule_defs:
        rule = session.scalar(
            select(AlertRule).where(
                AlertRule.workspace_id == workspace.id,
                AlertRule.company_id == company.id,
                AlertRule.rule_type == rule_type,
                AlertRule.is_synthetic.is_(True),
            )
        )
        if rule is None:
            rule = AlertRule(
                workspace_id=workspace.id,
                portfolio_id=portfolio.id,
                company_id=company.id,
                rule_type=rule_type,
                enabled=True,
                category=category_key,
                category_id=categories[category_key].id if category_key else None,
                price_pct_threshold=price_threshold,
                volume_multiplier=volume_multiplier,
                volume_lookback_days=20,
                is_synthetic=True,
            )
            session.add(rule)
            session.flush()
        rules[key] = rule

    for index, (dedupe_key, title, alert_type, rule_key) in enumerate(
        (
            ("synthetic-alert-price-001", "[DEMO ONLY] Illustrative EOD price move", "price_move", "synthetic-price-move"),
            ("synthetic-alert-results-002", "[DEMO ONLY] Illustrative results filing", "announcement", "synthetic-results-category"),
        )
    ):
        alert = session.scalar(
            select(Alert).where(
                Alert.workspace_id == workspace.id,
                Alert.dedupe_key == dedupe_key,
            )
        )
        if alert is None:
            session.add(
                Alert(
                    workspace_id=workspace.id,
                    company_id=company.id,
                    alert_rule_id=rules[rule_key].id,
                    alert_type=alert_type,
                    announcement_id=(
                        results_announcement.id
                        if alert_type == "announcement" and results_announcement is not None
                        else None
                    ),
                    title=title,
                    summary="Synthetic demonstration alert; no real market or filing event is asserted.",
                    status="unread",
                    dedupe_key=dedupe_key,
                    source_id=source_id,
                    is_synthetic=True,
                )
            )
            inserted += 1
    return inserted


def _seed_entity_matches(
    session: Session,
    workspace: Workspace,
    aliases: dict[str, CompanyAlias],
    source_id: UUID,
) -> int:
    inserted = 0
    for ticker, alias in aliases.items():
        source_entity_key = f"demo-ticker:{ticker}"
        candidate_key = f"company:{alias.company_id}"
        match = session.scalar(
            select(EntityMatch).where(
                EntityMatch.workspace_id == workspace.id,
                EntityMatch.source_id == source_id,
                EntityMatch.source_entity_key == source_entity_key,
                EntityMatch.candidate_key == candidate_key,
            )
        )
        if match is None:
            session.add(
                EntityMatch(
                    workspace_id=workspace.id,
                    source_id=source_id,
                    source_entity_key=source_entity_key,
                    candidate_key=candidate_key,
                    company_id=alias.company_id,
                    confidence=Decimal("1.0000"),
                    status="accepted",
                    rationale="Curated demo ticker mapping; not a runtime identity match.",
                    is_synthetic=True,
                )
            )
            inserted += 1
    return inserted


def _record_source_sync(
    session: Session, source: str, scope: str, fetched_at: datetime
) -> None:
    state = session.scalar(
        select(SourceSyncState).where(
            SourceSyncState.source == source,
            SourceSyncState.scope_key == scope,
        )
    )
    if state is None:
        state = SourceSyncState(source=source, scope_key=scope, status="success")
        session.add(state)
    state.last_attempt_at = fetched_at
    state.last_success_at = fetched_at
    state.status = "success"
    state.last_error_code = None


def seed_demo_database(session: Session, data_directory: Path) -> dict[str, int]:
    """Idempotently seeds a fully synthetic, provenance-labeled demo workspace."""
    data_directory = data_directory.resolve()
    fetched_at = datetime.now(timezone.utc)
    sources = _get_or_create_sources(session)
    seed_path = data_directory / COMPANY_FIXTURE
    aliases_added = load_seed_file(
        session,
        seed_path,
        include_ad_hoc=True,
        data_source_id=sources["company_seed"].id,
    )
    session.flush()
    workspace, user = _get_or_create_workspace(session)
    companies, aliases = _company_maps(session)
    portfolio = _seed_portfolio(session, workspace, seed_path, companies)
    categories = _seed_categories(
        session, data_directory / CATEGORY_FIXTURE
    )
    synthetic_source_id = sources["synthetic_demo"].id
    prices_added = _seed_market_prices(
        session,
        companies,
        aliases,
        synthetic_source_id,
        fetched_at,
    )
    announcements_added = _seed_announcements(
        session,
        data_directory / ANNOUNCEMENT_FIXTURE,
        categories,
        companies,
        synthetic_source_id,
        fetched_at,
    )
    documents, documents_added = _seed_documents(
        session,
        data_directory,
        companies,
        synthetic_source_id,
        fetched_at,
    )
    metrics = _seed_financial_records(
        session,
        companies,
        documents,
        synthetic_source_id,
        fetched_at,
    )
    guidance_added = _seed_guidance(
        session,
        companies,
        documents,
        metrics,
        synthetic_source_id,
    )
    reports_added = _seed_research_reports(
        session,
        workspace,
        companies,
        documents,
        synthetic_source_id,
        fetched_at,
    )
    alerts_added = _seed_alerts(
        session,
        workspace,
        portfolio,
        companies["RELIANCE"],
        categories,
        synthetic_source_id,
    )
    matches_added = _seed_entity_matches(
        session, workspace, aliases, sources["company_seed"].id
    )
    dataset = load_synthetic_contact_dataset(data_directory / NETWORK_FIXTURE)
    contacts_added = seed_synthetic_contacts(
        session,
        workspace_id=workspace.id,
        dataset=dataset,
    )
    classify_pending_announcements(session)
    for scope in ("companies", "announcements", "documents", "market_daily"):
        _record_source_sync(session, "synthetic_demo", scope, fetched_at)
    _record_source_sync(session, "synthetic_network_fixture", str(workspace.id), fetched_at)
    if session.scalar(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace.id,
            AuditLog.action == "demo_seed_completed",
            AuditLog.entity_id == DEMO_PORTFOLIO_ID,
        )
    ) is None:
        session.add(
            AuditLog(
                workspace_id=workspace.id,
                actor_user_id=user.id,
                action="demo_seed_completed",
                entity_type="portfolio",
                entity_id=DEMO_PORTFOLIO_ID,
                source_id=synthetic_source_id,
                metadata_json={
                    "synthetic": True,
                    "disclaimer": "All generated market, filing, financial, guidance, report, and network facts are demo fixtures.",
                },
                is_synthetic=True,
            )
        )
    session.commit()

    portfolio_count = session.scalar(
        select(func.count())
        .select_from(PortfolioCompany)
        .where(PortfolioCompany.portfolio_id == portfolio.id)
    )
    return {
        "companies_and_aliases_added": aliases_added,
        "portfolio_companies": int(portfolio_count or 0),
        "market_rows_added": prices_added,
        "announcements_added": announcements_added,
        "documents_added": documents_added,
        "financial_metrics": len(metrics),
        "guidance_added": guidance_added,
        "research_reports_added": reports_added,
        "alerts_added": alerts_added,
        "entity_matches_added": matches_added,
        "contacts_added": contacts_added,
    }
