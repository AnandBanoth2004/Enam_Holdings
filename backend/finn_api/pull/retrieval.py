from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.models import Document, DocumentChunk
from finn_api.pull.pdf_processing import ALLOWED_DOCUMENT_TYPES, DocumentType
from finn_api.pull.providers import EmbeddingProvider

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "been",
    "before",
    "between",
    "company",
    "could",
    "does",
    "from",
    "have",
    "into",
    "its",
    "more",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: UUID
    document_id: UUID
    ticker: str
    document_type: str
    document_name: str
    period_label: str | None
    page_number: int
    page_end: int
    source_url: str
    text: str
    score: float
    synthetic: bool


@dataclass(frozen=True)
class _CachedResult:
    expires_at: float
    result: tuple[EvidenceChunk, ...]


class RetrievalCache:
    def __init__(self, *, ttl_seconds: int = 300, max_entries: int = 256) -> None:
        if ttl_seconds < 0 or max_entries <= 0:
            raise ValueError("Cache TTL must be non-negative and max_entries positive.")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, _CachedResult] = {}

    def get(self, key: str) -> tuple[EvidenceChunk, ...] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            return None
        return entry.result

    def put(self, key: str, result: tuple[EvidenceChunk, ...]) -> None:
        if self.ttl_seconds == 0:
            return
        if len(self._entries) >= self.max_entries:
            oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
            del self._entries[oldest]
        self._entries[key] = _CachedResult(
            expires_at=time.monotonic() + self.ttl_seconds,
            result=result,
        )

    def clear(self) -> None:
        self._entries.clear()


def _lexical_score(query: str, text: str) -> float:
    query_terms = {
        term
        for term in _TOKEN_PATTERN.findall(query.casefold())
        if term not in _STOP_WORDS
    }
    if not query_terms:
        return 0.0
    document_terms = set(_TOKEN_PATTERN.findall(text.casefold()))
    overlap = len(query_terms & document_terms)
    if not overlap:
        return 0.0
    phrase_bonus = 0.15 if query.casefold() in text.casefold() else 0.0
    return min(1.0, overlap / len(query_terms) + phrase_bonus)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


class DocumentRetriever:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        cache: RetrievalCache | None = None,
        max_context_chars: int = 18000,
        max_candidates: int = 250,
    ) -> None:
        if max_context_chars <= 0 or max_candidates <= 0:
            raise ValueError("Retrieval context and candidate limits must be positive.")
        self.embedding_provider = embedding_provider
        self.cache = cache or RetrievalCache()
        self.max_context_chars = max_context_chars
        self.max_candidates = max_candidates

    def retrieve(
        self,
        session: Session,
        *,
        company_id: UUID,
        ticker: str,
        query: str,
        document_types: tuple[DocumentType, ...] = ALLOWED_DOCUMENT_TYPES,
        period_start: date | None = None,
        period_end: date | None = None,
        top_k: int = 8,
        include_synthetic: bool = False,
    ) -> tuple[EvidenceChunk, ...]:
        if not query.strip():
            raise ValueError("Research query must not be empty.")
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20.")
        if not document_types or any(item not in ALLOWED_DOCUMENT_TYPES for item in document_types):
            raise ValueError("Retrieval is restricted to the four supported primary document types.")

        statement = (
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.company_id == company_id,
                Document.document_type.in_(document_types),
                Document.is_primary_source.is_(True),
                Document.ingestion_status.in_(("extracted", "embedded")),
            )
        )
        if not include_synthetic:
            statement = statement.where(
                Document.synthetic.is_(False),
                DocumentChunk.synthetic.is_(False),
            )
        if period_start:
            statement = statement.where(
                Document.period_end.is_not(None),
                Document.period_end >= period_start,
            )
        if period_end:
            statement = statement.where(
                Document.period_start.is_not(None),
                Document.period_start <= period_end,
            )
        rows = session.execute(statement.limit(self.max_candidates)).all()
        eligible = [
            (chunk, document)
            for chunk, document in rows
            if urlparse(document.source_url).scheme == "https"
            and urlparse(document.source_url).hostname
        ]
        if not eligible:
            return ()

        manifest = "|".join(
            f"{document.id}:{document.content_hash}:{document.ingestion_status}:"
            f"{document.extracted_at.isoformat() if document.extracted_at else ''}"
            for _, document in eligible
        )
        vector_model = (
            self.embedding_provider.embedding_model
            if self.embedding_provider
            else "keyword-v1"
        )
        cache_material = (
            f"{company_id}|{ticker}|{query.casefold().strip()}|"
            f"{','.join(document_types)}|{period_start}|{period_end}|"
            f"{top_k}|{include_synthetic}|{vector_model}|{manifest}"
        )
        cache_key = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        query_vector: list[float] | None = None
        if self.embedding_provider is not None:
            vectors = self.embedding_provider.embed([query])
            if len(vectors) != 1 or not vectors[0] or any(
                not math.isfinite(value) for value in vectors[0]
            ):
                raise ValueError("Embedding provider returned an invalid query vector.")
            query_vector = vectors[0]

        ranked: list[tuple[float, DocumentChunk, Document]] = []
        is_postgres = session.get_bind().dialect.name == "postgresql"
        if query_vector is not None and is_postgres:
            distance = DocumentChunk.embedding.cosine_distance(query_vector)
            vector_statement = (
                select(DocumentChunk, Document, distance.label("distance"))
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    Document.company_id == company_id,
                    Document.document_type.in_(document_types),
                    Document.is_primary_source.is_(True),
                    Document.ingestion_status == "embedded",
                    DocumentChunk.embedding.is_not(None),
                    DocumentChunk.embedding_model == vector_model,
                )
            )
            if not include_synthetic:
                vector_statement = vector_statement.where(
                    Document.synthetic.is_(False),
                    DocumentChunk.synthetic.is_(False),
                )
            if period_start:
                vector_statement = vector_statement.where(Document.period_end >= period_start)
            if period_end:
                vector_statement = vector_statement.where(Document.period_start <= period_end)
            for chunk, document, distance_value in session.execute(
                vector_statement.order_by(distance).limit(self.max_candidates)
            ).all():
                ranked.append((1.0 - float(distance_value), chunk, document))
        elif query_vector is not None:
            for chunk, document in eligible:
                if (
                    chunk.embedding is not None
                    and chunk.embedding_model == vector_model
                    and len(chunk.embedding) == len(query_vector)
                ):
                    ranked.append(
                        (
                            _cosine_similarity(query_vector, chunk.embedding),
                            chunk,
                            document,
                        )
                    )

        ranked_ids = {chunk.id for _, chunk, _ in ranked}
        for chunk, document in eligible:
            if chunk.id in ranked_ids:
                continue
            lexical = _lexical_score(query, chunk.text)
            if lexical > 0:
                ranked.append((lexical, chunk, document))
        ranked.sort(key=lambda item: (-item[0], str(item[1].id)))

        result: list[EvidenceChunk] = []
        context_chars = 0
        for score, chunk, document in ranked:
            if score <= 0:
                continue
            if context_chars + len(chunk.text) > self.max_context_chars:
                continue
            result.append(
                EvidenceChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    ticker=ticker,
                    document_type=document.document_type,
                    document_name=document.title,
                    period_label=document.period_label,
                    page_number=chunk.page_start or 1,
                    page_end=chunk.page_end or chunk.page_start or 1,
                    source_url=document.source_url,
                    text=chunk.text,
                    score=score,
                    synthetic=document.synthetic or chunk.synthetic,
                )
            )
            context_chars += len(chunk.text)
            if len(result) >= top_k:
                break

        final_result = tuple(result)
        self.cache.put(cache_key, final_result)
        return final_result
