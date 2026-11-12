from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.db.models import Announcement, CompanyAlias, DataSource, SourceSyncState

logger = logging.getLogger(__name__)
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"
BSE_ANNOUNCEMENTS_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
)
_ALLOWED_EXCHANGE_HOSTS = ("nseindia.com", "bseindia.com")
_SAFE_FILE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
_INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class AnnouncementRecord:
    source: str
    source_key: str
    exchange: str
    ticker: str
    headline: str
    filed_at: datetime
    source_url: str
    original_document_url: str | None
    fetched_at: datetime
    payload_hash: str
    source_timestamp: datetime | None
    raw_payload: dict[str, Any]
    retrieval_status: str = "discovered"
    raw_document_path: str | None = None
    company_mapping_status: str = "unresolved"
    is_demo: bool = False


@dataclass(frozen=True)
class SourceRetrieval:
    source: str
    status: str
    fetched_at: datetime
    records_found: int
    error_code: str | None = None


@dataclass(frozen=True)
class AnnouncementBatch:
    records: tuple[AnnouncementRecord, ...]
    source_retrievals: tuple[SourceRetrieval, ...]
    demo_used: bool = False


@dataclass(frozen=True)
class RawDocumentResult:
    status: str
    path: str | None
    sha256: str | None
    error_code: str | None = None


class AnnouncementSourceAdapter(Protocol):
    source_name: str

    def fetch(
        self, start: date, end: date, ticker: str | None = None
    ) -> tuple[AnnouncementRecord, ...]: ...


class AnnouncementSourceError(RuntimeError):
    def __init__(self, source: str, code: str) -> None:
        super().__init__(f"{source} retrieval failed ({code}).")
        self.source = source
        self.code = code


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    for pattern in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(candidate, pattern)
            return parsed.replace(tzinfo=_INDIA_TIMEZONE) if parsed.tzinfo is None else parsed
        except ValueError:
            continue
    return None


def _payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _items_from_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "Table", "table", "announcements"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def _is_expected_response(payload: Any) -> bool:
    if isinstance(payload, list):
        return True
    return isinstance(payload, dict) and any(
        key in payload for key in ("data", "Table", "table", "announcements")
    )


def _record_from_fields(
    payload: dict[str, Any],
    *,
    source: str,
    exchange: str,
    fetched_at: datetime,
    ticker_filter: str | None = None,
) -> AnnouncementRecord | None:
    keys = {str(key).casefold(): key for key in payload}

    def value(*candidates: str) -> object:
        for candidate in candidates:
            key = keys.get(candidate.casefold())
            if key is not None and payload[key] not in (None, ""):
                return payload[key]
        return None

    raw_ticker = value("symbol", "scrip_cd", "scripcode", "ticker")
    raw_key = value("seq_id", "newsid", "news_id", "id", "attchmntfile")
    headline = value(
        "desc",
        "attchmnttext",
        "newssub",
        "headline",
        "subject",
        "sub",
    )
    timestamp = _parse_timestamp(
        value("an_dt", "dt_tm", "news_dt", "timestamp", "filed_at", "date")
    )
    direct_url = value("attchmntfile", "nsurl", "attachmenturl", "documenturl", "url")
    if not raw_key or not headline or timestamp is None:
        return None

    ticker = str(raw_ticker or ticker_filter or "").strip().upper()
    if exchange == "NSE":
        try:
            ticker = normalize_nse_ticker(ticker)
        except ValueError:
            return None
    if ticker_filter and ticker != ticker_filter:
        return None

    direct = str(direct_url).strip() if direct_url else ""
    if direct.startswith("//"):
        direct = f"https:{direct}"
    if direct.startswith("/"):
        direct = f"https://www.nseindia.com{direct}"
    if exchange == "NSE" and direct and not direct.startswith(("https://", "http://")):
        direct = f"https://nsearchives.nseindia.com/corporate/{direct.lstrip('/')}"
    if not direct.startswith(("https://", "http://")):
        direct = ""

    source_url = direct or (
        f"https://www.nseindia.com/get-quotes/equity?symbol={ticker}"
        if exchange == "NSE"
        else "https://www.bseindia.com/corporates/ann.html"
    )
    return AnnouncementRecord(
        source=source,
        source_key=str(raw_key).strip(),
        exchange=exchange,
        ticker=ticker,
        headline=str(headline).strip(),
        filed_at=timestamp,
        source_url=source_url,
        original_document_url=direct or None,
        fetched_at=fetched_at,
        payload_hash=_payload_hash(payload),
        source_timestamp=timestamp,
        raw_payload=payload,
    )


class NSEAnnouncementsAdapter:
    source_name = "nse_public_announcements"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "FINN research prototype (public filing retrieval)",
                "Referer": "https://www.nseindia.com/",
            },
            follow_redirects=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch(
        self, start: date, end: date, ticker: str | None = None
    ) -> tuple[AnnouncementRecord, ...]:
        if start > end:
            raise ValueError("start must be on or before end.")
        normalized_ticker = normalize_nse_ticker(ticker) if ticker else None
        try:
            response = self.client.get(
                NSE_ANNOUNCEMENTS_URL,
                params={
                    "index": "equities",
                    "from_date": start.strftime("%d-%m-%Y"),
                    "to_date": end.strftime("%d-%m-%Y"),
                    "symbol": normalized_ticker or "",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AnnouncementSourceError(self.source_name, "source_unavailable") from error

        if not _is_expected_response(payload):
            raise AnnouncementSourceError(self.source_name, "invalid_response_schema")
        fetched_at = datetime.now(timezone.utc)
        records = (
            _record_from_fields(
                item,
                source=self.source_name,
                exchange="NSE",
                fetched_at=fetched_at,
                ticker_filter=normalized_ticker,
            )
            for item in _items_from_response(payload)
        )
        return tuple(record for record in records if record is not None)


class BSEAnnouncementsAdapter:
    source_name = "bse_public_announcements"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "FINN research prototype (public filing retrieval)",
                "Referer": "https://www.bseindia.com/",
            },
            follow_redirects=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch(
        self, start: date, end: date, ticker: str | None = None
    ) -> tuple[AnnouncementRecord, ...]:
        if start > end:
            raise ValueError("start must be on or before end.")
        try:
            response = self.client.get(
                BSE_ANNOUNCEMENTS_URL,
                params={
                    "strCat": "-1",
                    "strPrevDate": start.strftime("%d/%m/%Y"),
                    "strScrip": ticker or "",
                    "strSearch": "P",
                    "strToDate": end.strftime("%d/%m/%Y"),
                    "strType": "C",
                    "subcategory": "-1",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AnnouncementSourceError(self.source_name, "source_unavailable") from error

        if not _is_expected_response(payload):
            raise AnnouncementSourceError(self.source_name, "invalid_response_schema")
        fetched_at = datetime.now(timezone.utc)
        records = (
            _record_from_fields(
                item,
                source=self.source_name,
                exchange="BSE",
                fetched_at=fetched_at,
                ticker_filter=ticker.strip().upper() if ticker else None,
            )
            for item in _items_from_response(payload)
        )
        return tuple(record for record in records if record is not None)


class DemoAnnouncementAdapter:
    source_name = "demo_fixture"

    def __init__(self, fixture_file: Path) -> None:
        self.fixture_file = fixture_file

    def fetch(
        self, start: date, end: date, ticker: str | None = None
    ) -> tuple[AnnouncementRecord, ...]:
        payload = json.loads(self.fixture_file.read_text(encoding="utf-8"))
        fetched_at = datetime.now(timezone.utc)
        records: list[AnnouncementRecord] = []
        for row in payload.get("announcements", []):
            if not isinstance(row, dict):
                continue
            timestamp = _parse_timestamp(row.get("filed_at"))
            if timestamp is None or not start <= timestamp.date() <= end:
                continue
            row_ticker = normalize_nse_ticker(str(row.get("ticker", "")))
            if ticker and normalize_nse_ticker(ticker) != row_ticker:
                continue
            source_key = str(row["source_key"])
            records.append(
                AnnouncementRecord(
                    source=self.source_name,
                    source_key=source_key,
                    exchange="NSE",
                    ticker=row_ticker,
                    headline=str(row["headline"]),
                    filed_at=timestamp,
                    source_url=f"fixture://announcements/{source_key}",
                    original_document_url=None,
                    fetched_at=fetched_at,
                    payload_hash=_payload_hash(row),
                    source_timestamp=timestamp,
                    raw_payload=row,
                    retrieval_status="demo_fixture",
                    company_mapping_status="unresolved",
                    is_demo=True,
                )
            )
        return tuple(records)


class AnnouncementDiscoveryService:
    def __init__(
        self,
        adapters: tuple[AnnouncementSourceAdapter, ...],
        *,
        demo_fallback: AnnouncementSourceAdapter | None = None,
        document_store: RawAnnouncementDocumentStore | None = None,
    ) -> None:
        self.adapters = adapters
        self.demo_fallback = demo_fallback
        self.document_store = document_store

    def discover(
        self, start: date, end: date, ticker: str | None = None
    ) -> AnnouncementBatch:
        if start > end:
            raise ValueError("start must be on or before end.")
        records: dict[tuple[str, str], AnnouncementRecord] = {}
        statuses: list[SourceRetrieval] = []
        for adapter in self.adapters:
            attempted_at = datetime.now(timezone.utc)
            try:
                source_records = adapter.fetch(start, end, ticker)
            except AnnouncementSourceError as error:
                logger.warning(
                    "Announcement source unavailable source=%s code=%s",
                    error.source,
                    error.code,
                )
                statuses.append(
                    SourceRetrieval(
                        source=error.source,
                        status="failed",
                        fetched_at=attempted_at,
                        records_found=0,
                        error_code=error.code,
                    )
                )
                continue
            statuses.append(
                SourceRetrieval(
                    source=adapter.source_name,
                    status="success",
                    fetched_at=datetime.now(timezone.utc),
                    records_found=len(source_records),
                )
            )
            for record in source_records:
                records[(record.source, record.source_key)] = record

        demo_used = not records and self.demo_fallback is not None
        if demo_used:
            demo_records = self.demo_fallback.fetch(start, end, ticker)
            statuses.append(
                SourceRetrieval(
                    source=self.demo_fallback.source_name,
                    status="demo_fallback",
                    fetched_at=datetime.now(timezone.utc),
                    records_found=len(demo_records),
                )
            )
            records.update(
                ((record.source, record.source_key), record) for record in demo_records
            )

        if self.document_store is not None:
            for key, record in tuple(records.items()):
                if record.original_document_url:
                    stored = self.document_store.download(record.original_document_url)
                    records[key] = with_document_result(record, stored)

        return AnnouncementBatch(
            records=tuple(sorted(records.values(), key=lambda record: record.filed_at, reverse=True)),
            source_retrievals=tuple(statuses),
            demo_used=demo_used,
        )


class RawAnnouncementDocumentStore:
    """Stores public PDF attachments under hash-only names from official exchange hosts."""

    def __init__(
        self,
        directory: Path,
        *,
        client: httpx.Client | None = None,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive.")
        self.directory = directory.resolve()
        self.max_bytes = max_bytes
        self.client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": "FINN research prototype (public filing retrieval)"},
            follow_redirects=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def download(self, url: str) -> RawDocumentResult:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in _ALLOWED_EXCHANGE_HOSTS
        ):
            return RawDocumentResult("rejected", None, None, "untrusted_document_host")

        try:
            with self.client.stream("GET", url) as response:
                response.raise_for_status()
                response_host = (urlparse(str(response.url)).hostname or "").lower()
                if not any(
                    response_host == domain or response_host.endswith(f".{domain}")
                    for domain in _ALLOWED_EXCHANGE_HOSTS
                ):
                    return RawDocumentResult("rejected", None, None, "untrusted_redirect_host")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        return RawDocumentResult("rejected", None, None, "document_too_large")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if not content.startswith(b"%PDF-"):
                    return RawDocumentResult("rejected", None, None, "not_a_pdf")
        except httpx.HTTPError as error:
            logger.warning(
                "Announcement document retrieval failed host=%s error_type=%s",
                hostname,
                type(error).__name__,
            )
            return RawDocumentResult("failed", None, None, "document_unavailable")

        digest = hashlib.sha256(content).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = _SAFE_FILE_NAME.sub("_", digest) + ".pdf"
        target = (self.directory / filename).resolve()
        if target.parent != self.directory:
            return RawDocumentResult("rejected", None, None, "invalid_storage_path")
        target.write_bytes(content)
        return RawDocumentResult("stored", str(target), digest)


def persist_announcement_batch(session: Session, batch: AnnouncementBatch) -> int:
    """Persist mapped exchange filings and source-poll freshness without classifying them."""
    inserted = 0
    for record in batch.records:
        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == record.exchange,
                CompanyAlias.normalized_symbol == record.ticker,
            )
        )
        if alias is None:
            continue
        data_source = session.scalar(
            select(DataSource).where(DataSource.source_key == record.source)
        )
        if data_source is None:
            data_source = DataSource(
                source_key=record.source,
                display_name=record.source.replace("_", " ").title(),
                source_type="synthetic_fixture" if record.is_demo else "exchange",
                base_url=None,
                is_primary=not record.is_demo,
                is_synthetic=record.is_demo,
            )
            session.add(data_source)
            session.flush()
        existing = session.scalar(
            select(Announcement).where(
                Announcement.source == record.source,
                Announcement.source_key == record.source_key,
            )
        )
        if existing is None:
            existing = Announcement(
                company_id=alias.company_id,
                source=record.source,
                source_key=record.source_key,
                source_url=record.source_url,
                headline=record.headline,
                filed_at=record.filed_at,
                category="unclassified",
                materiality="routine",
                source_payload_hash=record.payload_hash,
                source_timestamp=record.source_timestamp,
                retrieval_status=record.retrieval_status,
                raw_document_path=record.raw_document_path,
                source_payload=record.raw_payload,
                data_source_id=data_source.id,
                synthetic=record.is_demo,
                fetched_at=record.fetched_at,
            )
            session.add(existing)
            inserted += 1
        else:
            existing.company_id = alias.company_id
            existing.source_url = record.source_url
            existing.headline = record.headline
            existing.filed_at = record.filed_at
            existing.source_payload_hash = record.payload_hash
            existing.source_timestamp = record.source_timestamp
            existing.retrieval_status = record.retrieval_status
            existing.raw_document_path = record.raw_document_path
            existing.source_payload = record.raw_payload
            existing.data_source_id = data_source.id
            existing.synthetic = record.is_demo
            existing.fetched_at = record.fetched_at

    for retrieval in batch.source_retrievals:
        sync_state = session.scalar(
            select(SourceSyncState).where(
                SourceSyncState.source == retrieval.source,
                SourceSyncState.scope_key == "announcements",
            )
        )
        if sync_state is None:
            sync_state = SourceSyncState(
                source=retrieval.source,
                scope_key="announcements",
                status=retrieval.status,
            )
            session.add(sync_state)
        sync_state.last_attempt_at = retrieval.fetched_at
        if retrieval.status in ("success", "demo_fallback"):
            sync_state.last_success_at = retrieval.fetched_at
        sync_state.status = retrieval.status
        sync_state.last_error_code = retrieval.error_code

    session.commit()
    return inserted


def with_document_result(
    record: AnnouncementRecord, result: RawDocumentResult
) -> AnnouncementRecord:
    return replace(
        record,
        retrieval_status=result.status,
        raw_document_path=result.path,
    )
