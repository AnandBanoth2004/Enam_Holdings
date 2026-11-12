from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.pull.pdf_processing import ALLOWED_DOCUMENT_TYPES, DocumentType


class ResearchDiscoveryRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=40)

    @field_validator("ticker")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return normalize_nse_ticker(value)


class ResearchDocumentItem(BaseModel):
    id: UUID
    document_type: DocumentType
    title: str
    source_url: str
    period_label: str | None
    ingestion_status: str
    is_primary_source: bool
    is_synthetic: bool


class ResearchDiscoveryResponse(BaseModel):
    ticker: str
    company_name: str
    status: str
    fetched_at: datetime
    error_code: str | None
    documents: list[ResearchDocumentItem]


class ResearchIngestionRequest(BaseModel):
    expected_period: str | None = Field(default=None, max_length=40)
    max_chunk_tokens: int = Field(default=700, ge=40, le=1400)


class ResearchIngestionResponse(BaseModel):
    document_id: UUID
    status: str
    duplicate_of: UUID | None
    page_count: int
    chunk_count: int
    embedded_chunk_count: int
    embedding_model: str | None
    extraction_method: str | None
    period_label: str | None


class ResearchAnswerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=3, max_length=2000)
    document_types: list[DocumentType] = Field(
        default_factory=lambda: list(ALLOWED_DOCUMENT_TYPES),
        min_length=1,
        max_length=4,
    )
    period_start: date | None = None
    period_end: date | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    include_synthetic: bool = False

    @field_validator("ticker")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return normalize_nse_ticker(value)

    @field_validator("document_types")
    @classmethod
    def unique_document_types(cls, value: list[DocumentType]) -> list[DocumentType]:
        if len(set(value)) != len(value):
            raise ValueError("document_types must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end.")
        return self


class ResearchCitationResponse(BaseModel):
    chunk_id: UUID
    document_name: str
    reporting_period: str | None
    page_number: int
    source_url: str
    quote: str
    is_synthetic: bool


class ResearchClaimResponse(BaseModel):
    text: str
    claim_type: Literal["reported_fact", "calculation", "interpretation"]
    citations: list[ResearchCitationResponse] = Field(min_length=1)
    confidence: float | None


class ResearchAnswerResponse(BaseModel):
    ticker: str
    question: str
    status: Literal["complete", "evidence_only", "insufficient_evidence"]
    claims: list[ResearchClaimResponse]
    limitations: list[str]
    source_count: int
    is_synthetic: bool
    model_route: str | None
