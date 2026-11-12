from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class NetworkExperienceResponse(BaseModel):
    organization: str
    title: str | None
    sector: str | None
    start_date: date | None
    end_date: date | None
    ticker: str | None = None
    is_current: bool
    is_synthetic: bool


class NetworkEducationResponse(BaseModel):
    institution: str
    qualification: str | None
    field_of_study: str | None
    graduation_year: int | None
    is_synthetic: bool


class NetworkPathStep(BaseModel):
    contact_id: UUID
    name: str
    relationship_type: str
    strength: str | None
    evidence: str | None
    last_interaction: datetime | None


class NetworkContactResponse(BaseModel):
    id: UUID
    display_name: str
    current_role: str | None
    current_employer: str | None
    previous_employers: list[str]
    education: list[NetworkEducationResponse]
    graduation_year: int | None
    expertise: list[str]
    industry_experience: list[str]
    companies_worked_with: list[str]
    connection_type: str | None
    connection_distance: Literal[1, 2] | None
    last_interaction: datetime | None
    relationship_strength: str | None
    relationship_evidence: str | None
    relationship_path: list[NetworkPathStep]
    is_synthetic: bool
    experiences: list[NetworkExperienceResponse]


class NetworkContactSearchResponse(BaseModel):
    total: int
    contacts: list[NetworkContactResponse]


class NetworkPathResponse(BaseModel):
    contact_id: UUID
    distance: Literal[1, 2] | None
    path: list[NetworkPathStep]
    explanation: str


class CompanyEntityMatchResponse(BaseModel):
    contact_id: UUID
    contact_name: str
    confidence: float
    status: Literal["accepted", "proposed"]
    method: str
    evidence: str


class CompanyConnectionResponse(BaseModel):
    ticker: str
    company_name: str
    contacts: list[NetworkContactResponse]
    match_confidence: float
    match_evidence: list[str]
    entity_matches: list[CompanyEntityMatchResponse]


class NetworkRecommendationResponse(BaseModel):
    contact: NetworkContactResponse
    score: int
    connection_distance: Literal[1, 2]
    reasons: list[str]
    path: list[NetworkPathStep]
    evidence_quality: Literal["explicit_synthetic_fixture", "explicit_record"]
    workflow: Literal[
        "who_to_call",
        "second_degree_reach",
        "management_diligence",
        "sector_expertise",
        "keep_warm",
    ]


class NetworkRecommendationsResponse(BaseModel):
    workflow: Literal[
        "who_to_call",
        "second_degree_reach",
        "management_diligence",
        "sector_expertise",
        "keep_warm",
    ]
    ticker: str | None
    executive: str | None
    recommendations: list[NetworkRecommendationResponse]
    notice: str
