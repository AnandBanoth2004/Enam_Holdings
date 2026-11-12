from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from finn_api.pull.providers import ResearchModel
from finn_api.pull.retrieval import EvidenceChunk

ClaimType = Literal["reported_fact", "calculation", "interpretation"]


class EvidenceQuoteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(min_length=8, max_length=1200)


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    claim_type: ClaimType
    evidence_quotes: list[EvidenceQuoteDraft] = Field(min_length=1, max_length=5)
    confidence: float | None = Field(default=None, ge=0, le=1)


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimDraft] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class Citation(BaseModel):
    chunk_id: UUID
    document_name: str
    reporting_period: str | None
    page_number: int
    source_url: str
    quote: str
    is_synthetic: bool


class GroundedClaim(BaseModel):
    text: str
    claim_type: ClaimType
    citations: list[Citation] = Field(min_length=1)
    confidence: float | None = None


class GroundedAnswer(BaseModel):
    ticker: str
    question: str
    status: Literal["complete", "evidence_only", "insufficient_evidence"]
    claims: list[GroundedClaim]
    limitations: list[str]
    source_count: int
    is_synthetic: bool
    model_route: str | None


class AnswerGenerationError(ValueError):
    pass


def _normalized_quote(value: str) -> str:
    return " ".join(value.split()).casefold()


def _validated_claims(
    draft: AnswerDraft,
    evidence: tuple[EvidenceChunk, ...],
) -> list[GroundedClaim]:
    evidence_by_id = {str(item.chunk_id): item for item in evidence}
    claims: list[GroundedClaim] = []
    for candidate in draft.claims:
        citations: list[Citation] = []
        seen: set[str] = set()
        for cited in candidate.evidence_quotes:
            item = evidence_by_id.get(cited.chunk_id)
            if item is None:
                raise AnswerGenerationError(
                    "The model cited an evidence chunk that was not retrieved."
                )
            normalized_quote = _normalized_quote(cited.quote)
            if normalized_quote not in _normalized_quote(item.text):
                raise AnswerGenerationError(
                    "A model citation quote is not present verbatim in its source chunk."
                )
            if cited.chunk_id in seen:
                continue
            seen.add(cited.chunk_id)
            citations.append(
                Citation(
                    chunk_id=item.chunk_id,
                    document_name=item.document_name,
                    reporting_period=item.period_label,
                    page_number=item.page_number,
                    source_url=item.source_url,
                    quote=cited.quote,
                    is_synthetic=item.synthetic,
                )
            )
        if not citations:
            raise AnswerGenerationError("Every factual claim must cite retrieved evidence.")
        claims.append(
            GroundedClaim(
                text=candidate.text,
                claim_type=candidate.claim_type,
                citations=citations,
                confidence=candidate.confidence,
            )
        )
    return claims


def _extractive_draft(
    question: str,
    evidence: tuple[EvidenceChunk, ...],
) -> AnswerDraft:
    terms = set(re.findall(r"[a-z0-9]{2,}", question.casefold()))
    claims: list[ClaimDraft] = []
    for item in evidence:
        candidates = [
            " ".join(sentence.split())
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", item.text)
            if sentence.strip()
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda sentence: (
                -len(terms & set(re.findall(r"[a-z0-9]{2,}", sentence.casefold()))),
                len(sentence),
            )
        )
        quote = candidates[0][:1200].strip()
        if len(quote) < 8:
            continue
        claims.append(
            ClaimDraft(
                text=quote,
                claim_type="reported_fact",
                evidence_quotes=[
                    EvidenceQuoteDraft(chunk_id=str(item.chunk_id), quote=quote)
                ],
            )
        )
        if len(claims) >= 3:
            break
    return AnswerDraft(
        claims=claims,
        limitations=[
            "No language model was configured; returned statements are verbatim source excerpts, not generated analysis."
        ],
    )


def generate_grounded_answer(
    *,
    ticker: str,
    question: str,
    evidence: tuple[EvidenceChunk, ...],
    research_model: ResearchModel | None = None,
) -> GroundedAnswer:
    if not evidence:
        return GroundedAnswer(
            ticker=ticker,
            question=question,
            status="insufficient_evidence",
            claims=[],
            limitations=[
                "No eligible primary-source passages matched this question and its document filters."
            ],
            source_count=0,
            is_synthetic=False,
            model_route=None,
        )

    if research_model is None:
        draft = _extractive_draft(question, evidence)
        status: Literal["complete", "evidence_only", "insufficient_evidence"] = (
            "evidence_only" if draft.claims else "insufficient_evidence"
        )
    else:
        evidence_payload = [
            {
                "chunk_id": str(item.chunk_id),
                "document_name": item.document_name,
                "reporting_period": item.period_label or "",
                "page_number": str(item.page_number),
                "text": item.text,
            }
            for item in evidence
        ]
        raw_response = research_model.answer(
            question=question,
            evidence=evidence_payload,
        )
        try:
            draft = AnswerDraft.model_validate_json(raw_response)
        except ValidationError as error:
            raise AnswerGenerationError(
                "The research model response did not match the grounded-answer schema."
            ) from error
        status = "complete" if draft.claims else "insufficient_evidence"

    claims = _validated_claims(draft, evidence)
    if not claims:
        status = "insufficient_evidence"
    return GroundedAnswer(
        ticker=ticker,
        question=question,
        status=status,
        claims=claims,
        limitations=draft.limitations,
        source_count=len({item.document_id for item in evidence}),
        is_synthetic=any(item.synthetic for item in evidence),
        model_route=research_model.model if research_model else "extractive-evidence-v1",
    )
