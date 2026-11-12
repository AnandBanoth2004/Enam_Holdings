from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ResearchDimensionName = Literal[
    "business_snapshot",
    "financial_snapshot",
    "financial_trajectory",
    "balance_sheet_analysis",
    "cash_quality_analysis",
    "narrative_vs_numbers",
    "management_guidance",
    "bull_vs_bear",
]


class ResearchSourceReference(BaseModel):
    document_id: UUID
    document_name: str
    document_type: str
    reporting_period: str | None
    page_number: int | None
    source_url: str
    quote: str | None = None
    chunk_id: UUID | None = None
    is_synthetic: bool = False


class ResearchEvidenceClaim(BaseModel):
    text: str
    claim_type: Literal["reported_fact", "calculation", "interpretation"]
    citations: list[ResearchSourceReference] = Field(min_length=1)
    metric_key: str | None = None
    value: str | None = None
    currency: str | None = None
    unit_scale: str | None = None
    period_label: str | None = None
    reporting_basis: str | None = None
    from_period: str | None = None
    to_period: str | None = None


class ResearchGuidanceRow(BaseModel):
    statement_date: date | None
    quarter: str
    management_statement: str
    metric_key: str | None
    expected_result: str | None
    actual_result: str | None
    variance: str | None
    assessment: Literal[
        "exceeded", "met", "missed", "not_yet_verifiable"
    ]
    citations: list[ResearchSourceReference] = Field(min_length=1)


class ResearchSection(BaseModel):
    status: Literal["ready", "partial", "unavailable"]
    facts: list[ResearchEvidenceClaim] = Field(default_factory=list)
    calculations: list[ResearchEvidenceClaim] = Field(default_factory=list)
    interpretations: list[ResearchEvidenceClaim] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ResearchReportContent(BaseModel):
    business_snapshot: ResearchSection
    financial_snapshot: ResearchSection
    financial_trajectory: ResearchSection
    balance_sheet_analysis: ResearchSection
    cash_quality_analysis: ResearchSection
    narrative_vs_numbers: ResearchSection
    management_guidance: ResearchSection
    bull_vs_bear: ResearchSection


class FinancialResearchReportResponse(ResearchReportContent):
    report_id: UUID | None = None
    ticker: str
    company_name: str
    generated_at: datetime
    status: Literal["complete", "partial", "unavailable"]
    source_count: int
    source_manifest: list[ResearchSourceReference]
    model_route: str
    is_synthetic: bool = False


class CompanySearchItem(BaseModel):
    ticker: str
    exchange: str
    company_id: UUID
    company_name: str
    sector: str | None
    has_primary_documents: bool
    has_financial_data: bool


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanySearchItem]


class ResearchReportRequest(BaseModel):
    workspace_id: UUID
    reporting_basis: Literal["standalone", "consolidated"] = "consolidated"
    quarters: int = Field(default=4, ge=1, le=4)


class FinancialExtractionRequest(BaseModel):
    period_label: str = Field(min_length=1, max_length=40)
    period_start: date
    period_end: date
    period_type: Literal["quarter", "year"]
    reporting_basis: Literal["standalone", "consolidated"]
    currency: str = Field(min_length=3, max_length=3)
    unit_scale: str = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start.")
        return self


class FinancialExtractionResponse(BaseModel):
    document_id: UUID
    period_id: UUID
    period_label: str
    reporting_basis: str
    extracted_count: int
    metric_keys: list[str]
    ambiguous_metric_keys: list[str]
    values: dict[str, Decimal]


class FinancialMetricsResponse(BaseModel):
    ticker: str
    reporting_basis: str
    periods: list[dict[str, Any]]


class ResearchSourcesResponse(BaseModel):
    ticker: str
    sources: list[ResearchSourceReference]


__all__ = [
    "CompanySearchResponse",
    "FinancialExtractionRequest",
    "FinancialExtractionResponse",
    "FinancialMetricsResponse",
    "FinancialResearchReportResponse",
    "ResearchGuidanceRow",
    "ResearchReportRequest",
    "ResearchSection",
    "ResearchSourceReference",
    "ResearchSourcesResponse",
]
