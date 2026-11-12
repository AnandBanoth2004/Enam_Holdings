from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.announcements import (
    AnnouncementBatch,
    persist_announcement_batch,
)
from finn_api.db.models import (
    Announcement,
    AnnouncementCategory,
    Company,
    CompanyAlias,
    NetworkPerson,
    PersonExperience,
    Portfolio,
    PortfolioCompany,
    Workspace,
)
from finn_api.push.alerts import create_announcement_alerts
from finn_api.push.classification import (
    CATEGORY_KEYS,
    classify_announcement,
    summarize_announcement,
)
from finn_api.push.materiality import assess_materiality


@dataclass(frozen=True)
class NetworkContext:
    person_id: UUID
    display_name: str
    role: str | None
    organization: str
    match_reason: str
    synthetic: bool


@dataclass(frozen=True)
class AnnouncementView:
    id: UUID
    company_name: str
    ticker: str
    headline: str
    filed_at: datetime
    category: str
    summary: str
    original_filing_url: str
    extraction_confidence: Decimal | None
    source_metadata: dict[str, object]
    materiality_score: int | None
    priority: str
    materiality_reasons: tuple[str, ...]
    is_synthetic: bool
    network_context: tuple[NetworkContext, ...]


@dataclass(frozen=True)
class DigestResult:
    start: datetime
    end: datetime
    items: tuple[AnnouncementView, ...]


def _category_row(session: Session, key: str) -> AnnouncementCategory:
    row = session.scalar(
        select(AnnouncementCategory).where(
            AnnouncementCategory.category_key == key
        )
    )
    if row is None:
        row = AnnouncementCategory(
            category_key=key,
            display_name=key,
            priority=50,
            synthetic=False,
        )
        session.add(row)
        session.flush()
    return row


def process_announcement_batch(
    session: Session, batch: AnnouncementBatch
) -> dict[str, int]:
    """Persist filings, deterministically classify/score them, then fire rules."""
    inserted = persist_announcement_batch(session, batch)
    classified_count = 0
    alerts_created = 0
    for record in batch.records:
        announcement = session.scalar(
            select(Announcement).where(
                Announcement.source == record.source,
                Announcement.source_key == record.source_key,
            )
        )
        if announcement is None:
            continue
        classification = classify_and_score_announcement(session, announcement)
        announcement.synthetic = announcement.synthetic or record.is_demo
        classified_count += 1
        alerts_created += create_announcement_alerts(session, announcement)

    session.commit()
    return {
        "inserted": inserted,
        "classified": classified_count,
        "alerts_created": alerts_created,
        "supported_categories": len(CATEGORY_KEYS),
    }


def classify_and_score_announcement(
    session: Session, announcement: Announcement
) -> None:
    classification = classify_announcement(
        announcement.headline, announcement.body_text
    )
    is_portfolio_company = session.scalar(
        select(PortfolioCompany.id)
        .join(Portfolio, Portfolio.id == PortfolioCompany.portfolio_id)
        .where(
            PortfolioCompany.company_id == announcement.company_id,
            Portfolio.is_default.is_(True),
        )
    ) is not None
    assessment = assess_materiality(
        category=classification.category,
        headline=announcement.headline,
        body=announcement.body_text,
        is_portfolio_company=is_portfolio_company,
    )
    announcement.category = classification.category
    announcement.category_id = _category_row(
        session, classification.category
    ).id
    announcement.category_confidence = Decimal(str(classification.confidence))
    announcement.summary = summarize_announcement(
        announcement.headline, announcement.body_text
    )
    announcement.materiality_score = assessment.score
    announcement.materiality = assessment.priority
    announcement.materiality_reasons = list(assessment.reasons)


def classify_pending_announcements(session: Session) -> int:
    pending = session.scalars(
        select(Announcement).where(Announcement.materiality_score.is_(None))
    ).all()
    for announcement in pending:
        classify_and_score_announcement(session, announcement)
        create_announcement_alerts(session, announcement)
    return len(pending)


def _network_context_for_company(
    session: Session,
    *,
    workspace_id: UUID,
    company: Company,
    ticker: str,
) -> tuple[NetworkContext, ...]:
    if not company.sector:
        return ()
    rows = session.execute(
        select(NetworkPerson, PersonExperience)
        .join(PersonExperience, PersonExperience.person_id == NetworkPerson.id)
        .where(
            NetworkPerson.workspace_id == workspace_id,
            PersonExperience.workspace_id == workspace_id,
            (
                (PersonExperience.company_id == company.id)
                | (PersonExperience.sector == company.sector)
            ),
        )
    ).all()
    selected: dict[UUID, NetworkContext] = {}
    for person, experience in rows:
        exact_company = experience.company_id == company.id
        candidate = NetworkContext(
            person_id=person.id,
            display_name=person.display_name,
            role=experience.title,
            organization=experience.organization,
            match_reason=(
                f"Work/experience overlap at {ticker}."
                if exact_company
                else f"Experience in the {company.sector} sector."
            ),
            synthetic=person.synthetic or experience.synthetic,
        )
        previous = selected.get(person.id)
        if previous is None or exact_company:
            selected[person.id] = candidate
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                ticker not in item.match_reason,
                item.display_name.casefold(),
            ),
        )[:3]
    )


def _announcement_view(
    session: Session,
    announcement: Announcement,
    *,
    workspace_id: UUID | None,
) -> AnnouncementView:
    company = session.get(Company, announcement.company_id)
    alias = session.scalar(
        select(CompanyAlias)
        .where(CompanyAlias.company_id == announcement.company_id)
        .order_by(CompanyAlias.exchange != "NSE", CompanyAlias.normalized_symbol)
    )
    ticker = alias.normalized_symbol if alias else ""
    network = (
        _network_context_for_company(
            session,
            workspace_id=workspace_id,
            company=company,
            ticker=ticker,
        )
        if workspace_id is not None and company is not None
        else ()
    )
    source_metadata: dict[str, object] = {
        "source": announcement.source,
        "source_key": announcement.source_key,
        "retrieval_status": announcement.retrieval_status,
        "source_timestamp": announcement.source_timestamp,
        "fetched_at": announcement.fetched_at,
        "payload_hash": announcement.source_payload_hash,
        "data_source_id": announcement.data_source_id,
        "is_synthetic": announcement.synthetic,
    }
    return AnnouncementView(
        id=announcement.id,
        company_name=company.display_name if company else "Unknown company",
        ticker=ticker,
        headline=announcement.headline,
        filed_at=announcement.filed_at,
        category=announcement.category,
        summary=announcement.summary or summarize_announcement(
            announcement.headline, announcement.body_text
        ),
        original_filing_url=announcement.source_url,
        extraction_confidence=announcement.category_confidence,
        source_metadata=source_metadata,
        materiality_score=announcement.materiality_score,
        priority=announcement.materiality,
        materiality_reasons=tuple(announcement.materiality_reasons or ()),
        is_synthetic=announcement.synthetic,
        network_context=network,
    )


def get_announcement_detail(
    session: Session,
    announcement_id: UUID,
    *,
    workspace_id: UUID | None = None,
) -> AnnouncementView:
    announcement = session.get(Announcement, announcement_id)
    if announcement is None:
        raise LookupError("Announcement not found.")
    return _announcement_view(
        session, announcement, workspace_id=workspace_id
    )


def get_announcement_digest(
    session: Session,
    *,
    workspace_id: UUID,
    window: Literal["24h", "48h", "7d", "custom"] = "24h",
    start: datetime | None = None,
    end: datetime | None = None,
    tickers: tuple[str, ...] = (),
    categories: tuple[str, ...] = (),
    priorities: tuple[str, ...] = (),
    now: datetime | None = None,
) -> DigestResult:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("Current time must include a timezone.")
    if window == "custom":
        if start is None or end is None:
            raise ValueError("Custom digest windows require start and end datetimes.")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Custom digest datetimes must include timezone offsets.")
        window_start, window_end = start, end
    else:
        duration = {
            "24h": timedelta(hours=24),
            "48h": timedelta(hours=48),
            "7d": timedelta(days=7),
        }[window]
        window_start, window_end = current_time - duration, current_time
    if window_start > window_end:
        raise ValueError("Digest start must be on or before end.")

    portfolio = session.scalar(
        select(Portfolio).where(
            Portfolio.workspace_id == workspace_id,
            Portfolio.is_default.is_(True),
        )
    )
    if portfolio is None:
        raise LookupError("Workspace has no default portfolio.")
    company_ids = set(
        session.scalars(
            select(PortfolioCompany.company_id).where(
                PortfolioCompany.portfolio_id == portfolio.id
            )
        ).all()
    )
    query = select(Announcement).where(
        Announcement.company_id.in_(company_ids),
        Announcement.filed_at >= window_start,
        Announcement.filed_at <= window_end,
    )
    if categories:
        query = query.where(Announcement.category.in_(categories))
    if priorities:
        query = query.where(Announcement.materiality.in_(priorities))
    announcements = session.scalars(
        query.order_by(
            Announcement.materiality_score.desc(),
            Announcement.filed_at.desc(),
        )
    ).all()
    normalized_tickers = {
        ticker.strip().upper().removesuffix(".NS") for ticker in tickers
    }
    views: list[AnnouncementView] = []
    for announcement in announcements:
        view = _announcement_view(
            session, announcement, workspace_id=workspace_id
        )
        if normalized_tickers and view.ticker not in normalized_tickers:
            continue
        views.append(view)
    return DigestResult(window_start, window_end, tuple(views))


def get_portfolio_workspace(
    session: Session, workspace_id: UUID
) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise LookupError("Workspace not found.")
    return workspace
