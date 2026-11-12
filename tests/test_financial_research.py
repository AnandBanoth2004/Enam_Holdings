from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finn_api.db.base import Base
from finn_api.db.engine import get_db_session
from finn_api.db.models import (
    Company,
    CompanyAlias,
    Document,
    DocumentChunk,
    FinancialMetric,
    FinancialStatementPeriod,
    GuidanceAssessment,
    ManagementGuidance,
    ResearchReport,
    ResearchRun,
    User,
    Workspace,
    WorkspaceMember,
)
from finn_api.api.auth import get_current_user
from finn_api.main import app
from finn_api.pull.financial_extraction import (
    extract_financial_values,
    persist_document_financials,
)
from finn_api.pull.financial_research import build_financial_research_report
from finn_api.schemas.financial_research import FinancialResearchReportResponse


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _document(
    session: Session,
    company: Company,
    *,
    ticker: str,
    kind: str,
    title: str,
    period_label: str,
    period_start: date,
    period_end: date,
    text: str | None = None,
    synthetic: bool = False,
) -> Document:
    document = Document(
        company_id=company.id,
        document_type=kind,
        title=title,
        source_url=f"https://issuer.example/{ticker}/{period_label}-{kind}.pdf",
        source_name="issuer.example",
        period_start=period_start,
        period_end=period_end,
        period_label=period_label,
        reporting_basis="consolidated",
        content_hash=uuid4().hex,
        ingestion_status="extracted",
        is_primary_source=True,
        synthetic=synthetic,
        fetched_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
    )
    session.add(document)
    session.flush()
    if text:
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                page_start=8,
                page_end=8,
                section="Business Overview",
                text=text,
                token_count=len(text.split()),
                content_hash=uuid4().hex,
                synthetic=synthetic,
            )
        )
    return document


def _period(
    session: Session,
    company: Company,
    document: Document,
    *,
    period_label: str,
    start: date,
    end: date,
    period_type: str,
    values: dict[str, Decimal],
    synthetic: bool = False,
) -> FinancialStatementPeriod:
    period = FinancialStatementPeriod(
        company_id=company.id,
        document_id=document.id,
        fiscal_year=period_label,
        period_label=period_label,
        period_start=start,
        period_end=end,
        period_type=period_type,
        reporting_basis="consolidated",
        currency="INR",
        unit_scale="crore",
        is_synthetic=synthetic,
    )
    session.add(period)
    session.flush()
    for metric_key, value in values.items():
        session.add(
            FinancialMetric(
                statement_period_id=period.id,
                document_id=document.id,
                metric_key=metric_key,
                reported_value=value,
                currency="INR",
                unit_scale="crore",
                reporting_basis="consolidated",
                source_page=20,
                source_excerpt=f"{metric_key.replace('_', ' ').title()} | {value} crore",
                extraction_method="test_primary_text",
                is_synthetic=synthetic,
            )
        )
    session.flush()
    return period


def test_financial_extractor_preserves_units_pages_and_withholds_ambiguous_rows() -> None:
    values, ambiguous = extract_financial_values(
        [
            (
                14,
                "\n".join(
                    (
                        "Revenue from operations | ₹ 1,200 crore",
                        "EBITDA | 180 crore",
                        "Profit before tax | 120 crore",
                        "Profit after tax | (90) crore",
                        "Total borrowings | 250 crore",
                        "Cash and cash equivalents | 150 crore",
                        "Cash flow from operating activities | 80 crore",
                        "Capital expenditure | 50 crore",
                        "Trade receivables | 30 crore",
                        "Inventory | 22 crore",
                        "Trade payables | 18 crore",
                        "Borrowings | 1,200 crore | 1,050 crore",
                    )
                ),
            )
        ],
        currency="INR",
        default_unit_scale="crore",
    )
    by_key = {item.metric_key: item for item in values}

    assert by_key["revenue"].value == Decimal("1200")
    assert by_key["revenue"].page_number == 14
    assert by_key["revenue"].currency == "INR"
    assert by_key["pat"].value == Decimal("-90")
    assert by_key["capital_expenditure"].unit_scale == "crore"
    assert "total_debt" in ambiguous
    assert "total_debt" not in by_key
    assert by_key["cash_from_operations"].value == Decimal("80")
    assert by_key["trade_receivables"].value == Decimal("30")


def test_annual_statement_extraction_selects_current_period_and_reporting_basis() -> None:
    values, ambiguous = extract_financial_values(
        [
            (
                100,
                "Consolidated Financial Statements\nFINANCIAL_STATEMENT_LAYOUT:\n"
                "Consolidated Balance Sheet\nAs at 31st March, 2026 (INR in crore)\n"
                "Total Equity 10,85,866 10,09,626\n"
                "Borrowings 16 2,70,751 2,36,899\n"
                "Total Current Assets 5,94,249 4,99,270   Total Current Liabilities 5,41,254 4,53,737\n"
                "Inventories 7 1,66,941 1,46,062\n"
                "Trade Receivables 9 58,491 42,121\n"
                "Cash and Cash Equivalents 10 1,45,977 1,06,502   Loans 4,870 5,182\n"
                "Trade Payables 21 1,58,842 1,86,789\n"
                "Borrowings 20 1,03,670 1,10,631\n"
                "Total Assets 21,78,140 19,50,121   Total Liabilities 10,92,274 9,40,495",
            ),
            (
                101,
                "Consolidated Financial Statements\nFINANCIAL_STATEMENT_LAYOUT:\n"
                "Consolidated Statement of Profit and Loss\nFor the year ended 31st March, 2026\n"
                "Revenue from Operations 25 10,75,675 9,80,136\n"
                "Profit Before Share of Profit / (Loss) of Associates / Joint Ventures and Tax 1,23,162 1,06,017\n"
                "Profit After Tax 95,610 80,787\n"
                "Profit for the year 95,754 81,309",
            ),
            (
                103,
                "Consolidated Financial Statements\nFINANCIAL_STATEMENT_LAYOUT:\n"
                "Consolidated Statement of Cash Flows\nFor the year ended 31st March, 2026\n"
                "Net Cash Flow from Operating Activities 1,92,113 1,78,703\n"
                "Expenditure for Property, Plant and Equipment, Spectrum and Other Intangible Assets (1,22,916) (1,39,967)",
            ),
            (
                4,
                "For FY2025-26, consolidated revenues of INR 11,75,919 crore and EBITDA of INR 2,07,911 crore. "
                "Repeated extracted text: EBITDA of INR 2,07,911 crore.",
            ),
            (
                59,
                "Standalone Financial Statements\nFINANCIAL_STATEMENT_LAYOUT:\n"
                "Standalone Statement of Profit and Loss\nRevenue from Operations 5,24,105 5,32,792",
            ),
        ],
        currency="INR",
        default_unit_scale="crore",
        period_label="FY2025-26",
        reporting_basis="consolidated",
    )
    by_key = {item.metric_key: item for item in values}

    assert by_key["revenue"].value == Decimal("1075675")
    assert by_key["revenue"].page_number == 101
    assert by_key["ebitda"].value == Decimal("207911")
    assert by_key["pat"].value == Decimal("95610")
    assert by_key["pbt"].value == Decimal("123162")
    assert by_key["current_borrowings"].value == Decimal("103670")
    assert by_key["non_current_borrowings"].value == Decimal("270751")
    assert "total_debt" not in by_key
    assert by_key["total_equity"].value == Decimal("1085866")
    assert by_key["cash_and_equivalents"].value == Decimal("145977")
    assert by_key["current_assets"].value == Decimal("594249")
    assert by_key["current_liabilities"].value == Decimal("541254")
    assert by_key["cash_from_operations"].value == Decimal("192113")
    assert by_key["capital_expenditure"].value == Decimal("-122916")
    assert "revenue" not in ambiguous
    assert all(item.page_number != 59 for item in values)


def test_persist_financials_reassembles_layout_sections_from_document_chunks() -> None:
    engine = _engine()
    with Session(engine) as session:
        company = Company(
            legal_name="Layout Example Limited",
            display_name="Layout Example",
        )
        session.add(company)
        session.flush()
        document = _document(
            session,
            company,
            ticker="LAYOUT",
            kind="annual_report",
            title="Layout Example Annual Report FY2025-26",
            period_label="FY2025-26",
            period_start=date(2025, 4, 1),
            period_end=date(2026, 3, 31),
        )
        page_chunks = (
            (
                4,
                "Chairman Statement",
                "For FY2025-26, consolidated revenues of INR 11,75,919 crore "
                "and EBITDA of INR 2,07,911 crore.",
            ),
            (101, "Consolidated Financial Statements", "FY2025-26"),
            (
                101,
                "FINANCIAL_STATEMENT_LAYOUT:",
                "Consolidated Statement of Profit and Loss\n"
                "For the year ended 31st March, 2026\n"
                "Revenue from Operations 25 10,75,675 9,80,136\n"
                "Profit Before Share of Profit / (Loss) of Associates / Joint Ventures and Tax 1,23,162 1,06,017\n"
                "Profit After Tax 95,610 80,787",
            ),
        )
        for index, (page, section, text) in enumerate(page_chunks, start=1):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    page_start=page,
                    page_end=page,
                    section=section,
                    text=text,
                    token_count=len(text.split()),
                    content_hash=uuid4().hex,
                    synthetic=False,
                )
            )
        session.flush()
        result = persist_document_financials(
            session,
            document=document,
            period_label="FY2025-26",
            period_start=date(2025, 4, 1),
            period_end=date(2026, 3, 31),
            period_type="year",
            reporting_basis="consolidated",
            currency="INR",
            unit_scale="crore",
        )
        period = session.scalar(select(FinancialStatementPeriod))

    extracted = {item.metric_key: item.value for item in result.extracted}
    assert extracted["revenue"] == Decimal("1075675")
    assert extracted["ebitda"] == Decimal("207911")
    assert extracted["pbt"] == Decimal("123162")
    assert extracted["pat"] == Decimal("95610")
    assert period.fiscal_year == "2026"
    engine.dispose()


def test_report_calculations_are_deterministic_cited_and_exclude_synthetic_rows() -> None:
    engine = _engine()
    with Session(engine) as session:
        company = Company(
            legal_name="Example Primary Source Industries Limited",
            display_name="Example Industries",
            sector="Industrials",
        )
        session.add(company)
        session.flush()
        for label, start, end, values in (
            (
                "FY2023-24",
                date(2023, 4, 1),
                date(2024, 3, 31),
                {
                    "revenue": Decimal("1000"),
                    "ebitda": Decimal("150"),
                    "pbt": Decimal("100"),
                    "pat": Decimal("-75"),
                    "ebit": Decimal("120"),
                    "total_debt": Decimal("300"),
                    "cash_and_equivalents": Decimal("100"),
                    "cash_from_operations": Decimal("90"),
                    "capital_expenditure": Decimal("40"),
                    "trade_receivables": Decimal("100"),
                    "inventory": Decimal("120"),
                    "trade_payables": Decimal("80"),
                    "total_equity": Decimal("500"),
                    "total_assets": Decimal("900"),
                    "current_assets": Decimal("300"),
                    "current_liabilities": Decimal("200"),
                    "cost_of_goods_sold": Decimal("600"),
                },
            ),
            (
                "FY2024-25",
                date(2024, 4, 1),
                date(2025, 3, 31),
                {
                    "revenue": Decimal("1200"),
                    "ebitda": Decimal("180"),
                    "pbt": Decimal("120"),
                    "pat": Decimal("90"),
                    "ebit": Decimal("150"),
                    "current_borrowings": Decimal("100"),
                    "non_current_borrowings": Decimal("150"),
                    "cash_and_equivalents": Decimal("150"),
                    "cash_from_operations": Decimal("80"),
                    "capital_expenditure": Decimal("50"),
                    "trade_receivables": Decimal("150"),
                    "inventory": Decimal("130"),
                    "trade_payables": Decimal("100"),
                    "total_equity": Decimal("550"),
                    "total_assets": Decimal("950"),
                    "current_assets": Decimal("350"),
                    "current_liabilities": Decimal("220"),
                    "cost_of_goods_sold": Decimal("650"),
                },
            ),
        ):
            doc = _document(
                session,
                company,
                ticker="EXAMPLE",
                kind="annual_report",
                title=f"Example Annual Report {label}",
                period_label=label,
                period_start=start,
                period_end=end,
                text=(
                    "Business overview: the company operates industrial products "
                    "and services segments across domestic markets."
                ),
            )
            _period(
                session,
                company,
                doc,
                period_label=label,
                start=start,
                end=end,
                period_type="year",
                values=values,
            )
        synthetic_doc = _document(
            session,
            company,
            ticker="EXAMPLE",
            kind="annual_report",
            title="[DEMO] Synthetic later report",
            period_label="FY2025-26",
            period_start=date(2025, 4, 1),
            period_end=date(2026, 3, 31),
            synthetic=True,
        )
        _period(
            session,
            company,
            synthetic_doc,
            period_label="FY2025-26",
            start=date(2025, 4, 1),
            end=date(2026, 3, 31),
            period_type="year",
            values={"revenue": Decimal("999999")},
            synthetic=True,
        )

        report = build_financial_research_report(
            session,
            company_id=company.id,
            ticker="EXAMPLE",
        )
        validated = FinancialResearchReportResponse.model_validate(report)

    assert validated.financial_snapshot.observations[0]["period_label"] == "FY2024-25"
    margin = validated.financial_snapshot.calculations[0]
    assert margin.value == "15.0000"
    growth = next(
        item
        for item in validated.financial_trajectory.calculations
        if item.metric_key == "revenue_yoy_pct"
    )
    assert growth.value == "20.0000"
    free_cash_flow = next(
        item
        for item in validated.cash_quality_analysis.calculations
        if item.metric_key == "free_cash_flow"
    )
    assert Decimal(free_cash_flow.value) == Decimal("30")
    assert any(
        item.metric_key == "debt_equity_ratio"
        for item in validated.balance_sheet_analysis.calculations
    )
    assert any(
        item.metric_key == "total_debt"
        for item in validated.balance_sheet_analysis.calculations
    )
    assert any(
        item.metric_key == "working_capital_cycle_days"
        for item in validated.balance_sheet_analysis.calculations
    )
    assert any(
        item.metric_key == "roce_pct"
        for item in validated.balance_sheet_analysis.calculations
    )
    assert not any(
        item.metric_key == "pat_yoy_pct"
        for item in validated.financial_trajectory.calculations
    )
    pat_absolute_change = next(
        item
        for item in validated.financial_trajectory.calculations
        if item.metric_key == "pat_absolute_change"
    )
    assert Decimal(pat_absolute_change.value) == Decimal("165")
    assert any(
        "prior-year base is zero or negative" in limitation
        for limitation in validated.financial_trajectory.limitations
    )
    for section in (
        validated.business_snapshot,
        validated.financial_snapshot,
        validated.financial_trajectory,
        validated.balance_sheet_analysis,
        validated.cash_quality_analysis,
        validated.bull_vs_bear,
    ):
        for claim in [*section.facts, *section.calculations, *section.interpretations]:
            assert claim.citations
            assert all(not citation.is_synthetic for citation in claim.citations)
    assert "FY2025-26" not in {row["period_label"] for row in validated.financial_trajectory.observations}
    assert "buy/sell" in validated.bull_vs_bear.observations[0]["disclaimer"]
    engine.dispose()


def test_explicit_numerical_guidance_is_compared_to_matching_actuals_and_saved() -> None:
    engine = _engine()
    with Session(engine) as session:
        company = Company(
            legal_name="Guidance Example Limited",
            display_name="Guidance Example",
        )
        session.add(company)
        session.flush()
        transcript = _document(
            session,
            company,
            ticker="GUIDE",
            kind="earnings_call_transcript",
            title="Q4 FY26 Earnings Call Transcript",
            period_label="Q4 FY26",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            text=(
                "Management expects revenue growth of 10-12% in Q1 FY27. "
                "Management expects demand to remain resilient."
            ),
        )
        prior = _document(
            session,
            company,
            ticker="GUIDE",
            kind="quarterly_result",
            title="Q1 FY26 Results",
            period_label="Q1 FY26",
            period_start=date(2025, 4, 1),
            period_end=date(2025, 6, 30),
        )
        target = _document(
            session,
            company,
            ticker="GUIDE",
            kind="quarterly_result",
            title="Q1 FY27 Results",
            period_label="Q1 FY27",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        _period(
            session,
            company,
            prior,
            period_label="Q1 FY26",
            start=date(2025, 4, 1),
            end=date(2025, 6, 30),
            period_type="quarter",
            values={"revenue": Decimal("1000")},
        )
        _period(
            session,
            company,
            target,
            period_label="Q1 FY27",
            start=date(2026, 4, 1),
            end=date(2026, 6, 30),
            period_type="quarter",
            values={"revenue": Decimal("1200")},
        )

        report = build_financial_research_report(
            session,
            company_id=company.id,
            ticker="GUIDE",
            reporting_basis="consolidated",
        )
        session.commit()
        guidance_rows = session.scalars(select(ManagementGuidance)).all()
        assessments = session.scalars(select(GuidanceAssessment)).all()
        guidance = FinancialResearchReportResponse.model_validate(report).management_guidance

    identified = next(
        row for row in guidance.observations if row["metric_key"] == "revenue_growth_pct"
    )
    assert identified["quarter"] == "Q4 FY26"
    assert identified["target_period"] == "Q1 FY2027"
    assert identified["expected_result"] == "10–12%"
    assert identified["actual_result"] == "20.0 percent"
    assert identified["assessment"] == "exceeded"
    assert len(identified["citations"]) >= 3
    assert guidance_rows[0].target_low == Decimal("10")
    assert guidance_rows[0].target_high == Decimal("12")
    assert any(item.outcome == "exceeded" for item in assessments)
    engine.dispose()


def test_company_research_report_api_saves_report_and_exposes_company_routes() -> None:
    engine = _engine()
    with Session(engine) as session:
        workspace = Workspace(name="Research API test")
        user = User(auth_subject=uuid4(), email=f"{uuid4()}@example.test")
        company = Company(
            legal_name="API Research Company Limited",
            display_name="API Research Company",
        )
        session.add_all((workspace, user, company))
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
        )
        session.add(
            CompanyAlias(
                company_id=company.id,
                exchange="NSE",
                symbol="APIEX",
                normalized_symbol="APIEX",
            )
        )
        workspace_id = workspace.id
        user_id = user.id
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/research/companies/APIEX/report",
                json={"workspace_id": str(workspace_id)},
            )
            found = client.get(
                "/api/v1/research/companies/search",
                params={"q": "APIEX"},
            )
            saved = client.get(
                "/api/v1/research/companies/APIEX/report",
                params={"workspace_id": str(workspace_id)},
            )
            paths = client.get("/openapi.json").json()["paths"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert created.status_code == 200
    assert created.json()["status"] == "unavailable"
    assert created.json()["report_id"]
    assert found.status_code == 200
    assert found.json()["results"][0]["ticker"] == "APIEX"
    assert saved.status_code == 200
    assert saved.json()["report_id"] == created.json()["report_id"]
    assert {
        "/api/v1/research/companies/search",
        "/api/v1/research/companies/{ticker}/report",
        "/api/v1/research/companies/{ticker}/financial-metrics",
        "/api/v1/research/companies/{ticker}/financial-trajectory",
        "/api/v1/research/companies/{ticker}/guidance",
        "/api/v1/research/companies/{ticker}/narrative-comparison",
        "/api/v1/research/companies/{ticker}/bull-bear",
        "/api/v1/research/companies/{ticker}/sources",
        "/api/v1/research/documents/{document_id}/extract-financials",
    }.issubset(paths)
    with Session(engine) as session:
        assert session.scalar(select(ResearchReport)) is not None
        assert session.scalar(select(ResearchRun)) is not None
    engine.dispose()
