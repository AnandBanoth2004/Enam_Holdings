from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.models import (
    Alert,
    AlertRule,
    Announcement,
    AnnouncementCategory,
    Company,
    CompanyAlias,
    DataSource,
    MarketDaily,
    Portfolio,
    PortfolioCompany,
    Workspace,
)

DEFAULT_CATEGORY_ALERTS = ("results", "M&A", "management_change", "litigation")
FIXED_VOLUME_LOOKBACK = 20


@dataclass(frozen=True)
class AlertConfiguration:
    workspace_id: UUID
    ticker: str | None
    enabled: bool
    price_move_threshold_pct: Decimal | None
    volume_ratio_threshold: Decimal | None
    categories: tuple[str, ...]
    minimum_materiality_score: int | None
    volume_lookback_sessions: int = FIXED_VOLUME_LOOKBACK


def _workspace_portfolio(session: Session, workspace_id: UUID) -> Portfolio:
    portfolio = session.scalar(
        select(Portfolio)
        .where(
            Portfolio.workspace_id == workspace_id,
            Portfolio.is_default.is_(True),
        )
        .order_by(Portfolio.created_at)
    )
    if portfolio is None:
        raise LookupError("Workspace has no default portfolio.")
    return portfolio


def _company_for_ticker(session: Session, ticker: str | None) -> Company | None:
    if ticker is None:
        return None
    normalized = ticker.strip().upper().removesuffix(".NS")
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == normalized,
        )
    )
    if alias is None:
        raise LookupError(f"No NSE company mapping exists for ticker {normalized}.")
    return session.get(Company, alias.company_id)


def _find_rule(
    session: Session,
    *,
    workspace_id: UUID,
    portfolio_id: UUID,
    company_id: UUID | None,
    rule_type: str,
    category: str | None = None,
) -> AlertRule | None:
    query = select(AlertRule).where(
        AlertRule.workspace_id == workspace_id,
        AlertRule.portfolio_id == portfolio_id,
        AlertRule.company_id == company_id if company_id is not None else AlertRule.company_id.is_(None),
        AlertRule.rule_type == rule_type,
    )
    if category is None:
        query = query.where(AlertRule.category.is_(None))
    else:
        query = query.where(AlertRule.category == category)
    return session.scalar(query)


def _upsert_rule(
    session: Session,
    *,
    workspace_id: UUID,
    portfolio_id: UUID,
    company_id: UUID | None,
    rule_type: str,
    category: str | None,
    enabled: bool,
    price_threshold: Decimal | None = None,
    volume_multiplier: Decimal | None = None,
    priority_threshold: int | None = None,
    category_id: UUID | None = None,
) -> AlertRule:
    rule = _find_rule(
        session,
        workspace_id=workspace_id,
        portfolio_id=portfolio_id,
        company_id=company_id,
        rule_type=rule_type,
        category=category,
    )
    if rule is None:
        rule = AlertRule(
            workspace_id=workspace_id,
            portfolio_id=portfolio_id,
            company_id=company_id,
            rule_type=rule_type,
            category=category,
        )
        session.add(rule)
    rule.enabled = enabled
    rule.price_pct_threshold = price_threshold
    rule.volume_multiplier = volume_multiplier
    rule.priority_threshold = priority_threshold
    rule.volume_lookback_days = FIXED_VOLUME_LOOKBACK if rule_type == "volume_move" else None
    rule.category_id = category_id
    return rule


def configure_alerts(
    session: Session,
    *,
    workspace_id: UUID,
    ticker: str | None,
    enabled: bool,
    price_move_threshold_pct: Decimal | None,
    volume_ratio_threshold: Decimal | None,
    categories: tuple[str, ...],
    minimum_materiality_score: int | None,
) -> AlertConfiguration:
    portfolio = _workspace_portfolio(session, workspace_id)
    company = _company_for_ticker(session, ticker)
    company_id = company.id if company else None
    if company and session.scalar(
        select(PortfolioCompany.id).where(
            PortfolioCompany.portfolio_id == portfolio.id,
            PortfolioCompany.company_id == company.id,
        )
    ) is None:
        raise ValueError(f"{ticker} is not in this workspace's default portfolio.")

    _upsert_rule(
        session,
        workspace_id=workspace_id,
        portfolio_id=portfolio.id,
        company_id=company_id,
        rule_type="price_move",
        category=None,
        enabled=enabled and price_move_threshold_pct is not None,
        price_threshold=price_move_threshold_pct,
    )
    _upsert_rule(
        session,
        workspace_id=workspace_id,
        portfolio_id=portfolio.id,
        company_id=company_id,
        rule_type="volume_move",
        category=None,
        enabled=enabled and volume_ratio_threshold is not None,
        volume_multiplier=volume_ratio_threshold,
    )
    for rule in session.scalars(
        select(AlertRule).where(
            AlertRule.workspace_id == workspace_id,
            AlertRule.portfolio_id == portfolio.id,
            AlertRule.company_id == company_id if company_id is not None else AlertRule.company_id.is_(None),
            AlertRule.rule_type == "announcement_category",
        )
    ).all():
        rule.enabled = enabled and rule.category in categories

    for category in categories:
        category_row = session.scalar(
            select(AnnouncementCategory).where(
                AnnouncementCategory.category_key == category
            )
        )
        _upsert_rule(
            session,
            workspace_id=workspace_id,
            portfolio_id=portfolio.id,
            company_id=company_id,
            rule_type="announcement_category",
            category=category,
            enabled=enabled,
            category_id=category_row.id if category_row else None,
        )
    _upsert_rule(
        session,
        workspace_id=workspace_id,
        portfolio_id=portfolio.id,
        company_id=company_id,
        rule_type="announcement_priority",
        category=None,
        enabled=enabled and minimum_materiality_score is not None,
        priority_threshold=minimum_materiality_score,
    )
    session.commit()
    return get_alert_configuration(
        session, workspace_id=workspace_id, ticker=ticker
    )


def get_alert_configuration(
    session: Session, *, workspace_id: UUID, ticker: str | None
) -> AlertConfiguration:
    portfolio = _workspace_portfolio(session, workspace_id)
    company = _company_for_ticker(session, ticker)
    company_id = company.id if company else None
    rules = session.scalars(
        select(AlertRule).where(
            AlertRule.workspace_id == workspace_id,
            AlertRule.portfolio_id == portfolio.id,
            AlertRule.company_id == company_id if company_id is not None else AlertRule.company_id.is_(None),
        )
    ).all()
    enabled_rules = [rule for rule in rules if rule.enabled]
    price_rule = next((rule for rule in rules if rule.rule_type == "price_move"), None)
    volume_rule = next((rule for rule in rules if rule.rule_type == "volume_move"), None)
    priority_rule = next(
        (rule for rule in rules if rule.rule_type == "announcement_priority"),
        None,
    )
    return AlertConfiguration(
        workspace_id=workspace_id,
        ticker=ticker.strip().upper().removesuffix(".NS") if ticker else None,
        enabled=bool(enabled_rules),
        price_move_threshold_pct=(
            Decimal(price_rule.price_pct_threshold) if price_rule and price_rule.price_pct_threshold is not None else None
        ),
        volume_ratio_threshold=(
            Decimal(volume_rule.volume_multiplier) if volume_rule and volume_rule.volume_multiplier is not None else None
        ),
        categories=tuple(
            sorted(
                rule.category
                for rule in rules
                if rule.enabled
                and rule.rule_type == "announcement_category"
                and rule.category
            )
        ),
        minimum_materiality_score=(
            priority_rule.priority_threshold if priority_rule else None
        ),
    )


def _create_alert(
    session: Session,
    *,
    workspace_id: UUID,
    company_id: UUID,
    rule: AlertRule,
    alert_type: str,
    title: str,
    summary: str,
    dedupe_key: str,
    source_id: UUID | None,
    announcement_id: UUID | None = None,
    is_synthetic: bool = False,
) -> bool:
    existing = session.scalar(
        select(Alert.id).where(
            Alert.workspace_id == workspace_id,
            Alert.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return False
    session.add(
        Alert(
            workspace_id=workspace_id,
            company_id=company_id,
            announcement_id=announcement_id,
            alert_rule_id=rule.id,
            alert_type=alert_type,
            title=title[:240],
            summary=summary,
            status="unread",
            dedupe_key=dedupe_key,
            source_id=source_id,
            is_synthetic=is_synthetic,
        )
    )
    return True


def create_announcement_alerts(
    session: Session,
    announcement: Announcement,
    *,
    workspace_id: UUID | None = None,
) -> int:
    created = 0
    portfolios = session.execute(
        select(Portfolio, Workspace.id)
        .join(Workspace, Workspace.id == Portfolio.workspace_id)
        .join(PortfolioCompany, PortfolioCompany.portfolio_id == Portfolio.id)
        .where(PortfolioCompany.company_id == announcement.company_id)
    )
    if workspace_id is not None:
        portfolios = portfolios.where(Portfolio.workspace_id == workspace_id)
    portfolios = portfolios.all()
    for portfolio, workspace_id in portfolios:
        rules = session.scalars(
            select(AlertRule).where(
                AlertRule.workspace_id == workspace_id,
                AlertRule.portfolio_id == portfolio.id,
                AlertRule.enabled.is_(True),
                (
                    (AlertRule.company_id == announcement.company_id)
                    | (AlertRule.company_id.is_(None))
                ),
                AlertRule.rule_type.in_(
                    ("announcement_category", "announcement_priority")
                ),
            )
        ).all()
        for rule in rules:
            category_match = (
                rule.rule_type == "announcement_category"
                and rule.category == announcement.category
            )
            priority_match = (
                rule.rule_type == "announcement_priority"
                and rule.priority_threshold is not None
                and announcement.materiality_score is not None
                and announcement.materiality_score >= rule.priority_threshold
            )
            if not (category_match or priority_match):
                continue
            rule_description = (
                f"category={announcement.category}"
                if category_match
                else f"materiality score {announcement.materiality_score} >= configured threshold {rule.priority_threshold}"
            )
            created += _create_alert(
                session,
                workspace_id=workspace_id,
                company_id=announcement.company_id,
                rule=rule,
                alert_type="announcement",
                title=f"{announcement.materiality.title()} priority: {announcement.headline}",
                summary=(
                    f"Triggered by {rule_description}. "
                    f"Materiality: {announcement.materiality_score}/100. "
                    f"{' '.join(announcement.materiality_reasons or [])}"
                ),
                dedupe_key=f"announcement:{announcement.id}:rule:{rule.id}",
                source_id=announcement.data_source_id,
                announcement_id=announcement.id,
                is_synthetic=announcement.synthetic,
            )
    return created


def evaluate_market_alerts(
    session: Session,
    *,
    workspace_id: UUID,
    ticker: str | None = None,
    on_date: date | None = None,
) -> int:
    portfolio = _workspace_portfolio(session, workspace_id)
    company = _company_for_ticker(session, ticker)
    company_ids = set(
        session.scalars(
            select(PortfolioCompany.company_id).where(
                PortfolioCompany.portfolio_id == portfolio.id
            )
        ).all()
    )
    if company is not None:
        company_ids &= {company.id}
    if not company_ids:
        return 0
    created = 0
    for company_id in company_ids:
        latest_query = select(MarketDaily).where(MarketDaily.company_id == company_id)
        if on_date:
            latest_query = latest_query.where(MarketDaily.market_date == on_date)
        latest = session.scalar(
            latest_query.order_by(MarketDaily.market_date.desc()).limit(1)
        )
        if latest is None:
            continue
        previous = session.scalars(
            select(MarketDaily)
            .where(
                MarketDaily.company_id == company_id,
                MarketDaily.market_date < latest.market_date,
                MarketDaily.exchange == latest.exchange,
                MarketDaily.source == latest.source,
            )
            .order_by(MarketDaily.market_date.desc())
            .limit(FIXED_VOLUME_LOOKBACK)
        ).all()
        average_volume = (
            sum(Decimal(row.volume) for row in previous) / Decimal(len(previous))
            if len(previous) == FIXED_VOLUME_LOOKBACK
            else None
        )
        current_ratio = (
            Decimal(latest.volume) / average_volume
            if average_volume and average_volume > 0
            else None
        )
        latest.average_volume_20 = average_volume
        latest.volume_ratio = current_ratio
        rules = session.scalars(
            select(AlertRule).where(
                AlertRule.workspace_id == workspace_id,
                AlertRule.portfolio_id == portfolio.id,
                AlertRule.enabled.is_(True),
                (
                    (AlertRule.company_id == company_id)
                    | (AlertRule.company_id.is_(None))
                ),
                AlertRule.rule_type.in_(("price_move", "volume_move")),
            )
        ).all()
        company_name = session.get(Company, company_id)
        source_id = None
        data_source = session.scalar(
            select(DataSource).where(DataSource.source_key == latest.source)
        )
        if data_source:
            source_id = data_source.id
        for rule in rules:
            if (
                rule.rule_type == "price_move"
                and rule.price_pct_threshold is not None
                and latest.daily_change_pct is not None
                and abs(Decimal(latest.daily_change_pct)) >= Decimal(rule.price_pct_threshold)
            ):
                threshold = Decimal(rule.price_pct_threshold)
                created += _create_alert(
                    session,
                    workspace_id=workspace_id,
                    company_id=company_id,
                    rule=rule,
                    alert_type="price_move",
                    title=f"{company_name.display_name if company_name else 'Company'} EOD move {latest.daily_change_pct:+.2f}%",
                    summary=(
                        f"End-of-day price move {latest.daily_change_pct:+.2f}% met the configured "
                        f"absolute threshold of {threshold:.2f}% on {latest.market_date.isoformat()}. "
                        "This is daily close data, not an intraday alert."
                    ),
                    dedupe_key=f"market:{company_id}:{latest.market_date}:price:{rule.id}",
                    source_id=source_id,
                    is_synthetic=latest.synthetic,
                )
            elif (
                rule.rule_type == "volume_move"
                and rule.volume_multiplier is not None
                and current_ratio is not None
                and current_ratio >= Decimal(rule.volume_multiplier)
            ):
                created += _create_alert(
                    session,
                    workspace_id=workspace_id,
                    company_id=company_id,
                    rule=rule,
                    alert_type="volume_move",
                    title=f"{company_name.display_name if company_name else 'Company'} unusual EOD volume",
                    summary=(
                        f"Volume {latest.volume:,} was {current_ratio:.2f}x the mean of the "
                        f"previous {FIXED_VOLUME_LOOKBACK} trading sessions "
                        f"({average_volume:.0f}); configured threshold is "
                        f"{Decimal(rule.volume_multiplier):.2f}x on {latest.market_date.isoformat()}."
                    ),
                    dedupe_key=f"market:{company_id}:{latest.market_date}:volume:{rule.id}",
                    source_id=source_id,
                    is_synthetic=latest.synthetic,
                )
    session.commit()
    return created
