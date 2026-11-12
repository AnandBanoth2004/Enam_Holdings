from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.announcements import (
    AnnouncementBatch,
    AnnouncementRecord,
)
from finn_api.db.base import Base
from finn_api.db.models import (
    Alert,
    Announcement,
    AnnouncementCategory,
    Company,
    CompanyAlias,
    DataSource,
    Document,
    FinancialMetric,
    FinancialStatementPeriod,
    MarketDaily,
    Portfolio,
    PortfolioCompany,
    User,
    Workspace,
)
from finn_api.push.alerts import (
    configure_alerts,
    evaluate_market_alerts,
    get_alert_configuration,
)
from finn_api.push.classification import CATEGORY_KEYS, classify_announcement
from finn_api.push.materiality import assess_materiality, priority_for_score
from finn_api.push.results import compare_company_results, extract_result_metrics
from finn_api.push.service import (
    get_announcement_digest,
    process_announcement_batch,
)


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def _create_workspace_portfolio(session: Session):
    workspace = Workspace(name="Push test workspace")
    session.add(workspace)
    session.flush()
    company = Company(
        legal_name="Example Industries Limited",
        display_name="Example Industries",
        sector="Industrials",
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyAlias(
            company_id=company.id,
            exchange="NSE",
            symbol="EXAMPLE.NS",
            normalized_symbol="EXAMPLE",
        )
    )
    portfolio = Portfolio(
        workspace_id=workspace.id,
        name="Test portfolio",
        is_default=True,
    )
    session.add(portfolio)
    session.flush()
    session.add(PortfolioCompany(portfolio_id=portfolio.id, company_id=company.id))
    session.flush()
    return workspace, portfolio, company


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Quarterly financial results approved", "results"),
        ("Acquisition of a subsidiary", "M&A"),
        ("QIP fundraising proposal", "fund_raise"),
        ("CFO resignation", "management_change"),
        ("Regulatory penalty and legal proceedings", "litigation"),
        ("Credit rating downgrade", "credit_rating"),
        ("Promoter purchased shares", "insider_trading"),
        ("Earnings call transcript link", "earnings_call"),
        ("Investor conference meeting schedule", "investor_meetings"),
        ("Rating agency reaffirmed the credit rating", "credit_rating"),
        ("Interim dividend declared", "dividend"),
        ("Sub-division of equity shares", "bonus_split"),
        ("New plant and capacity expansion capex", "capex"),
        ("Press release: new product launch", "press_release"),
        ("Postal ballot notice", "postal_ballot"),
        ("Annual general meeting notice", "agm_egm"),
        ("Promoter pledged additional shares", "pledging"),
        ("Auditor appointment and compliance certificate", "unclassified"),
    ],
)
def test_classifier_covers_reference_labels(text: str, expected: str) -> None:
    assert classify_announcement(text).category == expected


def test_category_taxonomy_has_all_seventeen_reference_labels() -> None:
    assert len(CATEGORY_KEYS) == 17
    assert set(CATEGORY_KEYS) == {
        "results", "M&A", "fund_raise", "management_change", "litigation",
        "insider_trading", "earnings_call", "investor_meetings", "credit_rating",
        "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
        "agm_egm", "pledging", "unclassified",
    }


def test_materiality_rules_are_explainable_bounded_and_portfolio_sensitive() -> None:
    assessment = assess_materiality(
        category="M&A",
        headline="Acquisition for INR 250 crore",
        body="The board approved the transaction.",
        is_portfolio_company=True,
    )
    assert assessment.score == 75
    assert assessment.priority == "high"
    assert len(assessment.reasons) >= 4
    assert any("INR 250 crore" in reason for reason in assessment.reasons)

    unrelated = assess_materiality(
        category="unclassified",
        headline="Routine compliance filing",
        body=None,
        is_portfolio_company=False,
    )
    assert unrelated.score == 0
    assert unrelated.priority == "low"
    assert priority_for_score(80) == "critical"
    assert priority_for_score(60) == "high"
    assert priority_for_score(35) == "medium"
    assert priority_for_score(34) == "low"


def test_materiality_does_not_assume_foreign_currency_is_inr() -> None:
    foreign_amount = assess_materiality(
        category="M&A",
        headline="Acquisition for USD 250 crore",
        body=None,
        is_portfolio_company=False,
    )
    assert foreign_amount.score == 30
    assert any(
        "no eligible amount" in reason.casefold()
        for reason in foreign_amount.reasons
    )


@pytest.mark.parametrize(
    ("text", "expected_points"),
    [
        ("0.5 crore", 0),
        ("1 crore", 10),
        ("10 crore", 20),
        ("100 crore", 30),
        ("1,000 crore", 40),
        ("100 lakh", 10),
    ],
)
def test_materiality_amount_bands_use_normalized_crore_units(
    text: str, expected_points: int
) -> None:
    assessment = assess_materiality(
        category="unclassified",
        headline=f"Disclosed transaction value {text}",
        body=None,
        is_portfolio_company=False,
    )
    assert assessment.score == expected_points


def test_materiality_can_reach_critical_with_explained_signals() -> None:
    assessment = assess_materiality(
        category="credit_rating",
        headline="Credit rating downgrade for INR 1,000 crore",
        body=None,
        is_portfolio_company=True,
    )
    assert assessment.score == 89
    assert assessment.priority == "critical"


@pytest.mark.parametrize(
    ("headline", "expected"),
    [
        ("Illustrative dividend recommendation", "dividend"),
        ("Illustrative share subdivision proposal", "bonus_split"),
        ("Illustrative manufacturing investment plan", "capex"),
        ("Illustrative capital raising proposal", "fund_raise"),
    ],
)
def test_classifier_matches_demo_category_wording(headline: str, expected: str) -> None:
    assert classify_announcement(headline).category == expected


def test_result_extraction_omits_missing_and_ambiguous_values() -> None:
    extracted = extract_result_metrics(
        "Revenue: 1,200 crore; EBITDA: 210 crore; PBT: (40) crore; PAT: 25 crore",
    )
    assert set(extracted) == {"revenue", "ebitda", "pbt", "pat"}
    assert extracted["revenue"].value == Decimal("1200")
    assert extracted["pbt"].value == Decimal("-40")

    ambiguous = extract_result_metrics("Revenue: 100 crore; Revenue: 120 crore")
    assert "revenue" not in ambiguous
    no_unit = extract_result_metrics("PAT: 25")
    assert "pat" not in no_unit
    with_context = extract_result_metrics("PAT: 25", default_unit_scale="crore")
    assert with_context["pat"].unit_scale == "crore"


def _add_period(
    session: Session,
    *,
    company_id,
    period_end: date,
    values: dict[str, tuple[Decimal, str]],
    basis: str = "consolidated",
) -> FinancialStatementPeriod:
    start_month = period_end.month - 2
    start_year = period_end.year
    if start_month <= 0:
        start_month += 12
        start_year -= 1
    document = Document(
        company_id=company_id,
        document_type="quarterly_result",
        title=f"Filed result {period_end}",
        source_url=f"https://issuer.example/results/{period_end}/{basis}",
        source_name="issuer primary filing",
        content_hash=f"{period_end}-{basis}",
        fetched_at=datetime.now(timezone.utc),
        synthetic=False,
    )
    session.add(document)
    session.flush()
    period = FinancialStatementPeriod(
        company_id=company_id,
        document_id=document.id,
        fiscal_year=f"FY{period_end.year % 100}",
        period_label=f"Q{(period_end.month - 1) // 3 + 1} {period_end.year}",
        period_start=date(start_year, start_month, 1),
        period_end=period_end,
        period_type="quarter",
        reporting_basis=basis,
        currency="INR",
        unit_scale="crore",
    )
    session.add(period)
    session.flush()
    for metric_key, (value, unit) in values.items():
        session.add(
            FinancialMetric(
                statement_period_id=period.id,
                document_id=document.id,
                metric_key=metric_key,
                reported_value=value,
                currency="INR",
                unit_scale=unit,
                reporting_basis=basis,
                extraction_method="issuer_filing",
                is_synthetic=False,
            )
        )
    return period


def test_results_comparison_normalizes_units_and_handles_zero_negative_missing(db_engine) -> None:
    with Session(db_engine) as session:
        _, _, company = _create_workspace_portfolio(session)
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2025, 9, 30),
            values={
                "revenue": (Decimal("100"), "crore"),
                "ebitda": (Decimal("5"), "crore"),
                "pbt": (Decimal("12"), "crore"),
            },
        )
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2026, 6, 30),
            values={
                "revenue": (Decimal("11000"), "lakh"),
                "ebitda": (Decimal("-10"), "crore"),
                "pbt": (Decimal("-2"), "crore"),
                "pat": (Decimal("25"), "crore"),
            },
        )
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2026, 9, 30),
            values={
                "revenue": (Decimal("120"), "crore"),
                "ebitda": (Decimal("-5"), "crore"),
                "pbt": (Decimal("0"), "crore"),
                "pat": (Decimal("30"), "crore"),
            },
        )
        session.flush()
        current_period = session.scalar(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.period_end == date(2026, 9, 30)
            )
        )
        current_period.is_synthetic = True
        current_metrics = session.scalars(
            select(FinancialMetric).where(
                FinancialMetric.statement_period_id == current_period.id
            )
        ).all()
        for metric in current_metrics:
            metric.is_synthetic = True
        session.commit()

        result = compare_company_results(session, "EXAMPLE.NS")
        by_key = {metric.metric_key: metric for metric in result.metrics}
        assert by_key["revenue"].current.is_synthetic is True
        assert by_key["revenue"].qoq.value == Decimal("110")
        assert by_key["revenue"].qoq_percent_change.quantize(Decimal("0.01")) == Decimal("9.09")
        assert by_key["ebitda"].qoq_absolute_change == Decimal("5")
        assert by_key["ebitda"].qoq_percent_change is None
        assert "negative comparison base" in by_key["ebitda"].qoq_change_note
        assert by_key["pbt"].qoq_absolute_change == Decimal("2")
        assert by_key["pbt"].qoq_percent_change is None
        assert by_key["pat"].yoy.value is None
        assert "absent from the source period" in by_key["pat"].yoy.reason


def test_results_do_not_substitute_nonadjacent_quarters_or_reporting_basis(db_engine) -> None:
    with Session(db_engine) as session:
        _, _, company = _create_workspace_portfolio(session)
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2026, 3, 31),
            values={"revenue": (Decimal("100"), "crore")},
        )
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2026, 9, 30),
            values={"revenue": (Decimal("120"), "crore")},
        )
        _add_period(
            session,
            company_id=company.id,
            period_end=date(2026, 9, 30),
            values={"revenue": (Decimal("90"), "crore")},
            basis="standalone",
        )
        session.commit()

        result = compare_company_results(
            session, "EXAMPLE", reporting_basis="consolidated"
        )
        revenue = result.metrics[0]
        assert revenue.qoq.value is None
        assert "no other period was substituted" in revenue.qoq.reason
        assert revenue.yoy.value is None


def test_announcement_ingestion_to_prioritized_alert_is_idempotent(db_engine) -> None:
    with Session(db_engine) as session:
        workspace, portfolio, company = _create_workspace_portfolio(session)
        category = AnnouncementCategory(
            category_key="M&A", display_name="M&A", priority=100
        )
        session.add(category)
        session.flush()
        configure_alerts(
            session,
            workspace_id=workspace.id,
            ticker=None,
            enabled=True,
            price_move_threshold_pct=None,
            volume_ratio_threshold=None,
            categories=("M&A",),
            minimum_materiality_score=None,
        )
        filed_at = datetime(2026, 11, 11, 8, 30, tzinfo=timezone.utc)
        record = AnnouncementRecord(
            source="nse_public_announcements",
            source_key="nse-acquisition-1",
            exchange="NSE",
            ticker="EXAMPLE",
            headline="Board approves acquisition of a subsidiary",
            filed_at=filed_at,
            source_url="https://www.nseindia.com/filing/acquisition.pdf",
            original_document_url="https://www.nseindia.com/filing/acquisition.pdf",
            fetched_at=filed_at + timedelta(minutes=1),
            payload_hash="sha256:example",
            source_timestamp=filed_at,
            raw_payload={"symbol": "EXAMPLE"},
            is_demo=True,
        )
        batch = AnnouncementBatch((record,), (), False)

        first = process_announcement_batch(session, batch)
        announcement = session.scalar(select(Announcement))
        alert = session.scalar(select(Alert))
        assert first == {
            "inserted": 1,
            "classified": 1,
            "alerts_created": 1,
            "supported_categories": 17,
        }
        assert announcement.category == "M&A"
        assert announcement.summary
        assert announcement.materiality_score == 45
        assert announcement.materiality == "medium"
        assert announcement.source_url == record.source_url
        assert announcement.category_confidence > 0
        assert alert.announcement_id == announcement.id
        assert alert.is_synthetic is True
        assert "category=M&A" in alert.summary

        second = process_announcement_batch(session, batch)
        assert second["inserted"] == 0
        assert second["alerts_created"] == 0
        assert session.scalar(select(func.count()).select_from(Alert)) == 1

        digest = get_announcement_digest(
            session,
            workspace_id=workspace.id,
            window="custom",
            start=filed_at - timedelta(minutes=1),
            end=filed_at + timedelta(hours=1),
            categories=("M&A",),
            priorities=("medium",),
            now=filed_at + timedelta(hours=1),
        )
        assert len(digest.items) == 1
        assert digest.items[0].ticker == "EXAMPLE"
        assert digest.items[0].original_filing_url == record.source_url
        assert digest.items[0].source_metadata["source"] == record.source


def test_alert_configuration_reports_only_enabled_category_rules(db_engine) -> None:
    with Session(db_engine) as session:
        workspace, _, _ = _create_workspace_portfolio(session)
        configure_alerts(
            session,
            workspace_id=workspace.id,
            ticker=None,
            enabled=True,
            price_move_threshold_pct=None,
            volume_ratio_threshold=None,
            categories=("M&A", "results"),
            minimum_materiality_score=None,
        )
        updated = configure_alerts(
            session,
            workspace_id=workspace.id,
            ticker=None,
            enabled=True,
            price_move_threshold_pct=None,
            volume_ratio_threshold=None,
            categories=("M&A",),
            minimum_materiality_score=None,
        )
        assert updated.categories == ("M&A",)

        configure_alerts(
            session,
            workspace_id=workspace.id,
            ticker=None,
            enabled=False,
            price_move_threshold_pct=None,
            volume_ratio_threshold=None,
            categories=("M&A",),
            minimum_materiality_score=None,
        )
        disabled = get_alert_configuration(
            session, workspace_id=workspace.id, ticker=None
        )
        assert not disabled.enabled
        assert disabled.categories == ()


def test_volume_alert_uses_exactly_previous_twenty_sessions_and_deduplicates(db_engine) -> None:
    with Session(db_engine) as session:
        workspace, _, company = _create_workspace_portfolio(session)
        data_source = DataSource(
            source_key="yfinance",
            display_name="Yahoo Finance",
            source_type="market_data",
            is_primary=False,
        )
        session.add(data_source)
        session.flush()
        configure_alerts(
            session,
            workspace_id=workspace.id,
            ticker=None,
            enabled=True,
            price_move_threshold_pct=None,
            volume_ratio_threshold=Decimal("2"),
            categories=(),
            minimum_materiality_score=None,
        )
        first_date = date(2026, 10, 1)
        for day in range(20):
            session.add(
                MarketDaily(
                    company_id=company.id,
                    exchange="NSE",
                    market_date=first_date + timedelta(days=day),
                    close=Decimal("100"),
                    volume=1000,
                    source="yfinance",
                    data_source_id=data_source.id,
                    synthetic=False,
                    fetched_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
                )
            )
        alert_date = first_date + timedelta(days=20)
        session.add(
            MarketDaily(
                company_id=company.id,
                exchange="NSE",
                market_date=alert_date,
                close=Decimal("100"),
                daily_change_pct=Decimal("0"),
                volume=2500,
                source="yfinance",
                data_source_id=data_source.id,
                synthetic=False,
                fetched_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()

        assert evaluate_market_alerts(
            session, workspace_id=workspace.id, on_date=alert_date
        ) == 1
        current = session.scalar(
            select(MarketDaily).where(MarketDaily.market_date == alert_date)
        )
        assert current.average_volume_20 == Decimal("1000")
        assert current.volume_ratio == Decimal("2.5")
        assert evaluate_market_alerts(
            session, workspace_id=workspace.id, on_date=alert_date
        ) == 0
        alert = session.scalar(select(Alert))
        assert alert.alert_type == "volume_move"
        assert "previous 20 trading sessions" in alert.summary
        assert "daily close" not in alert.summary
