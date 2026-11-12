from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.api.auth import get_current_user, require_workspace_membership
from finn_api.db.engine import get_db_session
from finn_api.db.models import (
    Alert,
    Announcement,
    AnnouncementCategory,
    Company,
    Portfolio,
    PortfolioCompany,
    User,
)
from finn_api.push.alerts import (
    configure_alerts,
    create_announcement_alerts,
    evaluate_market_alerts,
    get_alert_configuration,
)
from finn_api.push.classification import (
    classify_announcement,
    summarize_announcement,
)
from finn_api.push.materiality import assess_materiality
from finn_api.push.results import compare_company_results
from finn_api.push.service import (
    get_announcement_detail,
    get_announcement_digest,
)
from finn_api.schemas.push import (
    AlertConfigurationRequest,
    AlertConfigurationResponse,
    AlertHistoryItem,
    AlertHistoryResponse,
    AnnouncementDigestResponse,
    AnnouncementResponse,
    ClassificationRequest,
    ClassificationResponse,
    MaterialityResponse,
    MarketAlertEvaluationResponse,
    ResultsComparisonResponse,
    AlertStatusUpdateRequest,
)

router = APIRouter(
    prefix="/push",
    tags=["push intelligence"],
    dependencies=[Depends(get_current_user)],
)


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "push_resource_not_found", "message": str(error)},
    )


def _announcement_response(item) -> AnnouncementResponse:
    payload = asdict(item)
    return AnnouncementResponse(**payload)


def _require_portfolio_announcement(
    session: Session,
    *,
    workspace_id: UUID,
    announcement_id: UUID,
) -> Announcement:
    announcement = session.scalar(
        select(Announcement)
        .join(PortfolioCompany, PortfolioCompany.company_id == Announcement.company_id)
        .join(Portfolio, Portfolio.id == PortfolioCompany.portfolio_id)
        .where(
            Announcement.id == announcement_id,
            Portfolio.workspace_id == workspace_id,
        )
    )
    if announcement is None:
        raise _not_found(LookupError("Announcement not found in this workspace's portfolio."))
    return announcement


@router.get("/digest", response_model=AnnouncementDigestResponse)
def announcement_digest(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    window: Literal["24h", "48h", "7d", "custom"] = "24h",
    start: datetime | None = None,
    end: datetime | None = None,
    ticker: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    priority: list[Literal["critical", "high", "medium", "low"]] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> AnnouncementDigestResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    try:
        result = get_announcement_digest(
            session,
            workspace_id=workspace_id,
            window=window,
            start=start,
            end=end,
            tickers=tuple(ticker),
            categories=tuple(category),
            priorities=tuple(priority),
        )
    except LookupError as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_digest_window", "message": str(error)},
        ) from error
    items = result.items[:limit]
    return AnnouncementDigestResponse(
        start=result.start,
        end=result.end,
        total=len(result.items),
        announcements=[_announcement_response(item) for item in items],
    )


@router.get(
    "/announcements/{announcement_id}",
    response_model=AnnouncementResponse,
)
def announcement_detail(
    announcement_id: UUID,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AnnouncementResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    _require_portfolio_announcement(
        session,
        workspace_id=workspace_id,
        announcement_id=announcement_id,
    )
    try:
        item = get_announcement_detail(
            session, announcement_id, workspace_id=workspace_id
        )
    except LookupError as error:
        raise _not_found(error) from error
    return _announcement_response(item)


@router.post("/classify", response_model=ClassificationResponse)
def classify_announcement_endpoint(
    request: ClassificationRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ClassificationResponse:
    announcement: Announcement | None = None
    if request.announcement_id:
        if request.workspace_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "workspace_required",
                    "message": "workspace_id is required when classifying a stored announcement.",
                },
            )
        require_workspace_membership(
            session,
            workspace_id=request.workspace_id,
            user=user,
        )
        announcement = _require_portfolio_announcement(
            session,
            workspace_id=request.workspace_id,
            announcement_id=request.announcement_id,
        )
        headline = announcement.headline
        body = announcement.body_text
        is_portfolio = session.scalar(
            select(PortfolioCompany.id)
            .join(Portfolio, Portfolio.id == PortfolioCompany.portfolio_id)
            .where(
                Portfolio.workspace_id == request.workspace_id,
                PortfolioCompany.company_id == announcement.company_id,
                Portfolio.is_default.is_(True),
            )
        ) is not None
    else:
        headline = request.headline or ""
        body = request.body
        is_portfolio = request.is_portfolio_company

    classification = classify_announcement(headline, body)
    assessment = assess_materiality(
        category=classification.category,
        headline=headline,
        body=body,
        is_portfolio_company=is_portfolio,
    )
    summary = summarize_announcement(headline, body)
    if announcement is not None:
        category = session.scalar(
            select(AnnouncementCategory).where(
                AnnouncementCategory.category_key == classification.category
            )
        )
        if category is None:
            category = AnnouncementCategory(
                category_key=classification.category,
                display_name=classification.category,
                priority=50,
                synthetic=False,
            )
            session.add(category)
            session.flush()
        announcement.category = classification.category
        announcement.category_id = category.id
        announcement.category_confidence = Decimal(str(classification.confidence))
        announcement.summary = summary
        announcement.materiality_score = assessment.score
        announcement.materiality = assessment.priority
        announcement.materiality_reasons = list(assessment.reasons)
        create_announcement_alerts(
            session,
            announcement,
            workspace_id=request.workspace_id,
        )
        session.commit()

    return ClassificationResponse(
        category=classification.category,
        confidence=classification.confidence,
        matched_terms=list(classification.matched_terms),
        summary=summary,
        materiality_score=assessment.score,
        priority=assessment.priority,
        reasons=list(assessment.reasons),
    )


@router.get(
    "/announcements/{announcement_id}/materiality",
    response_model=MaterialityResponse,
)
def materiality_explanation(
    announcement_id: UUID,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MaterialityResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    announcement = _require_portfolio_announcement(
        session,
        workspace_id=workspace_id,
        announcement_id=announcement_id,
    )
    return MaterialityResponse(
        announcement_id=announcement.id,
        score=announcement.materiality_score or 0,
        priority=announcement.materiality,
        reasons=announcement.materiality_reasons or ["Materiality has not been assessed yet."],
    )


def _config_response(configuration) -> AlertConfigurationResponse:
    return AlertConfigurationResponse(
        workspace_id=configuration.workspace_id,
        ticker=configuration.ticker,
        enabled=configuration.enabled,
        price_move_threshold_pct=configuration.price_move_threshold_pct,
        volume_ratio_threshold=configuration.volume_ratio_threshold,
        categories=list(configuration.categories),
        minimum_materiality_score=configuration.minimum_materiality_score,
        volume_lookback_sessions=configuration.volume_lookback_sessions,
    )


@router.get("/alerts/config", response_model=AlertConfigurationResponse)
def read_alert_configuration(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    ticker: str | None = None,
    session: Session = Depends(get_db_session),
) -> AlertConfigurationResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    try:
        configuration = get_alert_configuration(
            session, workspace_id=workspace_id, ticker=ticker
        )
    except LookupError as error:
        raise _not_found(error) from error
    return _config_response(configuration)


@router.put("/alerts/config", response_model=AlertConfigurationResponse)
def update_alert_configuration(
    request: AlertConfigurationRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AlertConfigurationResponse:
    require_workspace_membership(session, workspace_id=request.workspace_id, user=user)
    try:
        configuration = configure_alerts(
            session,
            workspace_id=request.workspace_id,
            ticker=request.ticker,
            enabled=request.enabled,
            price_move_threshold_pct=request.price_move_threshold_pct,
            volume_ratio_threshold=request.volume_ratio_threshold,
            categories=tuple(request.categories),
            minimum_materiality_score=request.minimum_materiality_score,
        )
    except LookupError as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_alert_configuration", "message": str(error)},
        ) from error
    return _config_response(configuration)


@router.get("/alerts/history", response_model=AlertHistoryResponse)
def alert_history(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    ticker: str | None = None,
    alert_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> AlertHistoryResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    query = select(Alert).where(Alert.workspace_id == workspace_id)
    if alert_type:
        query = query.where(Alert.alert_type == alert_type)
    if ticker:
        from finn_api.db.models import CompanyAlias

        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == "NSE",
                CompanyAlias.normalized_symbol == ticker.strip().upper().removesuffix(".NS"),
            )
        )
        if alias is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "ticker_not_found", "message": "No NSE mapping exists for ticker."},
            )
        query = query.where(Alert.company_id == alias.company_id)
    rows = session.scalars(query.order_by(Alert.created_at.desc())).all()
    return AlertHistoryResponse(
        workspace_id=workspace_id,
        total=len(rows),
        alerts=[
            AlertHistoryItem(
                id=alert.id,
                company_name=(
                    session.get(Company, alert.company_id).display_name
                    if alert.company_id and session.get(Company, alert.company_id)
                    else None
                ),
                alert_type=alert.alert_type,
                title=alert.title,
                summary=alert.summary,
                status=alert.status,
                created_at=alert.created_at,
                announcement_id=alert.announcement_id,
                dedupe_key=alert.dedupe_key,
                is_synthetic=alert.is_synthetic,
            )
            for alert in rows[:limit]
        ],
    )


@router.patch("/alerts/{alert_id}/status", response_model=AlertHistoryItem)
def update_alert_status(
    alert_id: UUID,
    request: AlertStatusUpdateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AlertHistoryItem:
    require_workspace_membership(session, workspace_id=request.workspace_id, user=user)
    alert = session.scalar(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.workspace_id == request.workspace_id,
        )
    )
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "alert_not_found", "message": "Alert not found in this workspace."},
        )
    alert.status = request.status
    alert.read_at = datetime.now(timezone.utc) if request.status == "read" else None
    session.commit()
    company = session.get(Company, alert.company_id) if alert.company_id else None
    return AlertHistoryItem(
        id=alert.id,
        company_name=company.display_name if company else None,
        alert_type=alert.alert_type,
        title=alert.title,
        summary=alert.summary,
        status=alert.status,
        created_at=alert.created_at,
        announcement_id=alert.announcement_id,
        dedupe_key=alert.dedupe_key,
        is_synthetic=alert.is_synthetic,
    )


@router.post(
    "/alerts/evaluate",
    response_model=MarketAlertEvaluationResponse,
)
def evaluate_eod_alerts(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    ticker: str | None = None,
    on_date: date | None = None,
    session: Session = Depends(get_db_session),
) -> MarketAlertEvaluationResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    try:
        count = evaluate_market_alerts(
            session,
            workspace_id=workspace_id,
            ticker=ticker,
            on_date=on_date,
        )
    except LookupError as error:
        raise _not_found(error) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_ticker", "message": str(error)},
        ) from error
    return MarketAlertEvaluationResponse(
        workspace_id=workspace_id,
        ticker=ticker.strip().upper().removesuffix(".NS") if ticker else None,
        alerts_created=count,
    )


@router.get(
    "/results/{ticker}/comparisons",
    response_model=ResultsComparisonResponse,
)
def results_comparisons(
    ticker: str,
    reporting_basis: str | None = Query(default=None, pattern="^(standalone|consolidated)$"),
    session: Session = Depends(get_db_session),
) -> ResultsComparisonResponse:
    try:
        result = compare_company_results(
            session, ticker, reporting_basis=reporting_basis
        )
    except LookupError as error:
        raise _not_found(error) from error
    return ResultsComparisonResponse(
        ticker=result.ticker,
        company_name=result.company_name,
        reporting_basis=result.reporting_basis,
        currency=result.currency,
        unit_scale=result.unit_scale,
        current_period=result.current_period,
        metrics=[
            {
                "metric_key": item.metric_key,
                "current": asdict(item.current),
                "qoq": asdict(item.qoq),
                "yoy": asdict(item.yoy),
                "qoq_absolute_change": item.qoq_absolute_change,
                "qoq_percent_change": item.qoq_percent_change,
                "qoq_change_note": item.qoq_change_note,
                "yoy_absolute_change": item.yoy_absolute_change,
                "yoy_percent_change": item.yoy_percent_change,
                "yoy_change_note": item.yoy_change_note,
            }
            for item in result.metrics
        ],
    )
