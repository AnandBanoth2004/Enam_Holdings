from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finn_api.push.classification import CATEGORY_KEYS

AnnouncementCategoryKey = Literal[
    "results",
    "M&A",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
]
PriorityKey = Literal["critical", "high", "medium", "low"]


class NetworkContextResponse(BaseModel):
    person_id: UUID
    display_name: str
    role: str | None
    organization: str
    match_reason: str
    synthetic: bool


class AnnouncementResponse(BaseModel):
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
    materiality_reasons: list[str]
    is_synthetic: bool
    network_context: list[NetworkContextResponse]


class AnnouncementDigestResponse(BaseModel):
    start: datetime
    end: datetime
    total: int
    announcements: list[AnnouncementResponse]


class ClassificationRequest(BaseModel):
    announcement_id: UUID | None = None
    workspace_id: UUID | None = None
    headline: str | None = Field(default=None, min_length=1, max_length=4000)
    body: str | None = Field(default=None, max_length=50000)
    is_portfolio_company: bool = False

    @field_validator("headline")
    @classmethod
    def require_headline_without_id(cls, value: str | None, info):
        if info.data.get("announcement_id") is None and not value:
            raise ValueError("headline is required when announcement_id is not supplied.")
        return value


class ClassificationResponse(BaseModel):
    category: str
    confidence: float
    matched_terms: list[str]
    summary: str
    materiality_score: int
    priority: PriorityKey
    reasons: list[str]
    method: Literal["deterministic_rules_v1"] = "deterministic_rules_v1"


class MaterialityResponse(BaseModel):
    announcement_id: UUID
    score: int
    priority: PriorityKey
    reasons: list[str]


class AlertConfigurationRequest(BaseModel):
    workspace_id: UUID
    ticker: str | None = None
    enabled: bool = True
    price_move_threshold_pct: Decimal | None = Field(default=Decimal("3"), gt=0, le=100)
    volume_ratio_threshold: Decimal | None = Field(default=Decimal("2"), gt=0, le=100)
    categories: list[AnnouncementCategoryKey] = Field(
        default_factory=lambda: ["results", "M&A", "management_change", "litigation"]
    )
    minimum_materiality_score: int | None = Field(default=35, ge=0, le=100)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str | None) -> str | None:
        return value.strip().upper().removesuffix(".NS") if value else None

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[AnnouncementCategoryKey]):
        if len(set(value)) != len(value):
            raise ValueError("categories must not contain duplicates.")
        return value


class AlertConfigurationResponse(BaseModel):
    workspace_id: UUID
    ticker: str | None
    enabled: bool
    price_move_threshold_pct: Decimal | None
    volume_ratio_threshold: Decimal | None
    categories: list[str]
    minimum_materiality_score: int | None
    volume_lookback_sessions: int = 20


class AlertHistoryItem(BaseModel):
    id: UUID
    company_name: str | None
    alert_type: str
    title: str
    summary: str | None
    status: str
    created_at: datetime
    announcement_id: UUID | None
    dedupe_key: str
    is_synthetic: bool


class AlertHistoryResponse(BaseModel):
    workspace_id: UUID
    total: int
    alerts: list[AlertHistoryItem]


class AlertStatusUpdateRequest(BaseModel):
    workspace_id: UUID
    status: Literal["read", "unread"]


class MarketAlertEvaluationResponse(BaseModel):
    workspace_id: UUID
    ticker: str | None
    alerts_created: int
    volume_baseline_sessions: int = 20
    market_data_semantics: Literal["end_of_day"] = "end_of_day"


class PeriodValueResponse(BaseModel):
    value: Decimal | None
    period_label: str | None
    period_end: date | None
    currency: str | None
    unit_scale: str | None
    reporting_basis: str | None
    source_url: str | None
    is_synthetic: bool = False
    reason: str | None


class MetricComparisonResponse(BaseModel):
    metric_key: str
    current: PeriodValueResponse
    qoq: PeriodValueResponse
    yoy: PeriodValueResponse
    qoq_absolute_change: Decimal | None
    qoq_percent_change: Decimal | None
    qoq_change_note: str | None
    yoy_absolute_change: Decimal | None
    yoy_percent_change: Decimal | None
    yoy_change_note: str | None


class ResultsComparisonResponse(BaseModel):
    ticker: str
    company_name: str
    reporting_basis: str
    currency: str
    unit_scale: str
    current_period: str
    metrics: list[MetricComparisonResponse]


class PushResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
