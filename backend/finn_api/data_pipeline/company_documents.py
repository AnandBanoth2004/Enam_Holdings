from __future__ import annotations

import hashlib
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urldefrag, urljoin, urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.db.models import Document, SourceSyncState

logger = logging.getLogger(__name__)
_DOCUMENT_TYPE_PATTERNS = (
    ("annual_report", re.compile(r"annual[\s_-]*reports?", re.IGNORECASE)),
    (
        "quarterly_result",
        re.compile(
            r"quarterly[\s_-]*(results?|reports?|financials?)"
            r"|financial[\s_-]*results?"
            r"|q[1-4][\s_-]*(?:fy)?\d{2,4}.{0,30}results?"
            r"|results?.{0,20}(?:q[1-4]|quarter)",
            re.IGNORECASE,
        ),
    ),
    (
        "earnings_call_transcript",
        re.compile(
            r"(?:earnings|analyst|con.?call|conference\s+call|results?\s+call)"
            r".{0,40}transcript"
            r"|transcript.{0,40}(?:earnings|analyst|con.?call|conference\s+call|results?\s+call)"
            r"|investor.{0,20}(?:call|conference).{0,20}transcript"
            r"|transcript.{0,20}investor.{0,20}(?:call|conference)",
            re.IGNORECASE,
        ),
    ),
    (
        "investor_presentation",
        re.compile(r"(investor|analyst|earnings).{0,30}(presentation|deck)|presentations?", re.IGNORECASE),
    ),
)
_IR_TERMS = re.compile(
    r"(investor|annual|quarter|result|financial|transcript|concall|presentation)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WebsiteResolution:
    url: str | None
    discovery_reference: str | None


class IssuerWebsiteResolver(Protocol):
    def resolve(self, ticker: str) -> WebsiteResolution: ...


class YFinanceIssuerWebsiteResolver:
    """Uses Yahoo Finance only to locate an issuer website, never as research evidence."""

    def resolve(self, ticker: str) -> WebsiteResolution:
        import yfinance as yf

        try:
            profile = yf.Ticker(f"{ticker}.NS").get_info()
        except Exception as error:
            logger.warning(
                "Issuer website lookup failed ticker=%s error_type=%s",
                ticker,
                type(error).__name__,
            )
            return WebsiteResolution(None, "yfinance_company_profile")
        website = profile.get("website") if isinstance(profile, dict) else None
        if not isinstance(website, str):
            return WebsiteResolution(None, "yfinance_company_profile")
        parsed = urlparse(website if "://" in website else f"https://{website}")
        if parsed.scheme != "https" or not parsed.hostname:
            return WebsiteResolution(None, "yfinance_company_profile")
        return WebsiteResolution(parsed.geturl(), "yfinance_company_profile")


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = next((value for key, value in attrs if key.lower() == "href"), None)
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
        if tag.lower() == "a":
            self._href = None
            self._text = []


@dataclass(frozen=True)
class DiscoveredCompanyDocument:
    ticker: str
    document_type: str
    title: str
    source_url: str
    source_name: str
    discovery_page_url: str
    content_hash: str
    ingestion_status: str = "discovered"
    is_primary_source: bool = True


@dataclass(frozen=True)
class CompanyDocumentDiscoveryResult:
    ticker: str
    status: str
    fetched_at: datetime
    issuer_website: str | None
    discovery_reference: str | None
    documents: tuple[DiscoveredCompanyDocument, ...]
    error_code: str | None = None


class CompanyDocumentDiscoveryService:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        website_resolver: IssuerWebsiteResolver | None = None,
        max_pages: int = 12,
        max_page_bytes: int = 3 * 1024 * 1024,
    ) -> None:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive.")
        if max_page_bytes <= 0:
            raise ValueError("max_page_bytes must be positive.")
        self.client = client or httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "FINN research prototype (issuer public documents)"},
            follow_redirects=False,
        )
        self._owns_client = client is None
        self.website_resolver = website_resolver or YFinanceIssuerWebsiteResolver()
        self.max_pages = max_pages
        self.max_page_bytes = max_page_bytes

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def discover(
        self,
        ticker: str,
        *,
        issuer_website: str | None = None,
        allowed_document_hosts: tuple[str, ...] = (),
    ) -> CompanyDocumentDiscoveryResult:
        symbol = normalize_nse_ticker(ticker)
        resolution = (
            WebsiteResolution(issuer_website, None)
            if issuer_website
            else self.website_resolver.resolve(symbol)
        )
        if not resolution.url:
            return CompanyDocumentDiscoveryResult(
                ticker=symbol,
                status="unavailable",
                fetched_at=datetime.now(timezone.utc),
                issuer_website=None,
                discovery_reference=resolution.discovery_reference,
                documents=(),
                error_code="issuer_website_not_found",
            )

        start_url = resolution.url
        parsed_start = urlparse(start_url)
        if parsed_start.scheme != "https" or not parsed_start.hostname:
            return CompanyDocumentDiscoveryResult(
                ticker=symbol,
                status="unavailable",
                fetched_at=datetime.now(timezone.utc),
                issuer_website=start_url,
                discovery_reference=resolution.discovery_reference,
                documents=(),
                error_code="invalid_issuer_website",
            )

        trusted_hosts = {parsed_start.hostname.lower()}
        trusted_hosts.update(host.lower().strip(".") for host in allowed_document_hosts)
        queue = deque([(start_url, 0)])
        visited: set[str] = set()
        discovered: dict[str, DiscoveredCompanyDocument] = {}
        failed_pages = 0
        successful_pages = 0

        while queue and len(visited) < self.max_pages:
            page_url, depth = queue.popleft()
            page_url, _ = urldefrag(page_url)
            if page_url in visited or not _is_trusted_url(page_url, trusted_hosts):
                continue
            visited.add(page_url)

            try:
                with self.client.stream("GET", page_url) as response:
                    response.raise_for_status()
                    final_url = str(response.url)
                    content_type = response.headers.get("content-type", "").casefold()
                    if "html" not in content_type:
                        continue
                    content: list[bytes] = []
                    total_bytes = 0
                    for chunk in response.iter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > self.max_page_bytes:
                            content = []
                            break
                        content.append(chunk)
            except httpx.HTTPError as error:
                failed_pages += 1
                logger.warning(
                    "Issuer IR page unavailable ticker=%s host=%s error_type=%s",
                    symbol,
                    urlparse(page_url).hostname,
                    type(error).__name__,
                )
                continue

            if not content:
                failed_pages += 1
                continue
            if not _is_trusted_url(final_url, trusted_hosts):
                failed_pages += 1
                continue

            parser = _AnchorParser()
            parser.feed(b"".join(content).decode("utf-8", errors="replace"))
            successful_pages += 1
            for href, anchor_text in parser.links:
                candidate = urldefrag(urljoin(final_url, href))[0]
                if not _is_http_url(candidate):
                    continue
                if not _is_trusted_url(candidate, trusted_hosts):
                    continue
                title = anchor_text.strip() or Path(urlparse(candidate).path).name or candidate
                document_type = _classify_document(f"{title} {urlparse(candidate).path}")
                if document_type:
                    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                    discovered[candidate] = DiscoveredCompanyDocument(
                        ticker=symbol,
                        document_type=document_type,
                        title=title[:500],
                        source_url=candidate,
                        source_name=urlparse(candidate).hostname or "issuer website",
                        discovery_page_url=final_url,
                        content_hash=digest,
                    )
                elif depth < 2 and _IR_TERMS.search(f"{title} {candidate}"):
                    queue.append((candidate, depth + 1))

        documents = tuple(
            sorted(discovered.values(), key=lambda document: (document.document_type, document.title.lower()))
        )
        if not documents:
            status = (
                "partial"
                if failed_pages and successful_pages
                else "failed"
                if failed_pages
                else "no_documents"
            )
            error_code = (
                "some_pages_unavailable"
                if status == "partial"
                else "issuer_site_unavailable"
                if status == "failed"
                else None
            )
        else:
            status = "partial" if failed_pages else "success"
            error_code = "some_pages_unavailable" if failed_pages else None
        return CompanyDocumentDiscoveryResult(
            ticker=symbol,
            status=status,
            fetched_at=datetime.now(timezone.utc),
            issuer_website=start_url,
            discovery_reference=resolution.discovery_reference,
            documents=documents,
            error_code=error_code,
        )


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _is_trusted_url(url: str, trusted_hosts: set[str]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and any(host == trusted or host.endswith(f".{trusted}") for trusted in trusted_hosts)
    )


def _classify_document(text: str) -> str | None:
    for document_type, pattern in _DOCUMENT_TYPE_PATTERNS:
        if pattern.search(text):
            return document_type
    return None


def persist_company_documents(
    session: Session,
    result: CompanyDocumentDiscoveryResult,
    *,
    company_id: UUID | None,
) -> int:
    inserted = 0
    if company_id is not None:
        for document in result.documents:
            existing = session.scalar(
                select(Document)
                .where(
                    Document.company_id == company_id,
                    Document.source_url == document.source_url,
                    Document.ingestion_status != "superseded",
                )
                .order_by(Document.fetched_at.desc())
                .limit(1)
            )
            if existing is not None:
                existing.fetched_at = result.fetched_at
                existing.title = document.title
                existing.document_type = document.document_type
                existing.source_name = document.source_name
                existing.is_primary_source = document.is_primary_source
                if existing.ingestion_status == "discovered":
                    existing.content_hash = document.content_hash
                    existing.ingestion_status = document.ingestion_status
                continue
            session.add(
                Document(
                    company_id=company_id,
                    document_type=document.document_type,
                    title=document.title,
                    source_url=document.source_url,
                    source_name=document.source_name,
                    content_hash=document.content_hash,
                    ingestion_status=document.ingestion_status,
                    is_primary_source=document.is_primary_source,
                    fetched_at=result.fetched_at,
                )
            )
            inserted += 1

    sync_state = session.scalar(
        select(SourceSyncState).where(
            SourceSyncState.source == "issuer_ir",
            SourceSyncState.scope_key == f"documents:{result.ticker}",
        )
    )
    if sync_state is None:
        sync_state = SourceSyncState(
            source="issuer_ir",
            scope_key=f"documents:{result.ticker}",
            status=result.status,
        )
        session.add(sync_state)
    sync_state.status = result.status
    sync_state.last_attempt_at = result.fetched_at
    sync_state.last_error_code = result.error_code
    if result.status in ("success", "partial", "no_documents"):
        sync_state.last_success_at = result.fetched_at

    session.commit()
    return inserted
