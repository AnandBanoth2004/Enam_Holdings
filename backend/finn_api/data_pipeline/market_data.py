from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from finn_api.data_pipeline.validation import (
    DataValidationError,
    calculate_market_metrics,
    normalize_nse_ticker,
    validate_ohlcv,
)

logger = logging.getLogger(__name__)
SOURCE_NAME = "yfinance"
EXCHANGE_TIMEZONE = ZoneInfo("Asia/Kolkata")


class MarketHistoryFetcher(Protocol):
    def __call__(self, symbol: str, start: date, end_exclusive: date) -> pd.DataFrame: ...


class MarketDataCache(Protocol):
    def load(self, ticker: str, start: date, end: date) -> pd.DataFrame | None: ...

    def store(self, ticker: str, start: date, end: date, frame: pd.DataFrame) -> None: ...

    def mark_attempt(
        self, ticker: str, status: str, error_code: str | None, attempted_at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class MarketDataResult:
    ticker: str
    data: pd.DataFrame
    source: str
    fetched_at: datetime
    status: str
    data_frequency: str = "daily_eod"
    is_live: bool = False
    is_demo: bool = False
    error_code: str | None = None
    detail: str | None = None


@dataclass
class InMemoryMarketCache:
    """Small process-local cache for tests and development; Postgres is durable storage."""

    ttl: timedelta = timedelta(hours=6)
    _entries: dict[tuple[str, date, date], tuple[datetime, pd.DataFrame]] = field(
        default_factory=dict
    )
    attempts: dict[str, tuple[str, str | None, datetime]] = field(default_factory=dict)

    def load(self, ticker: str, start: date, end: date) -> pd.DataFrame | None:
        entry = self._entries.get((ticker, start, end))
        if entry is None:
            return None
        fetched_at, frame = entry
        if datetime.now(timezone.utc) - fetched_at > self.ttl:
            del self._entries[(ticker, start, end)]
            return None
        return frame.copy(deep=True)

    def store(self, ticker: str, start: date, end: date, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        self._entries[(ticker, start, end)] = (datetime.now(timezone.utc), frame.copy(deep=True))

    def mark_attempt(
        self, ticker: str, status: str, error_code: str | None, attempted_at: datetime
    ) -> None:
        self.attempts[ticker] = (status, error_code, attempted_at)


def _yfinance_history(symbol: str, start: date, end_exclusive: date) -> pd.DataFrame:
    import yfinance as yf

    return yf.Ticker(f"{symbol}.NS").history(
        start=start.isoformat(),
        end=end_exclusive.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        raise_errors=True,
    )


class MarketDataService:
    """Fetch and normalize daily NSE bars; the adapter never describes them as live prices."""

    def __init__(
        self,
        *,
        fetcher: MarketHistoryFetcher = _yfinance_history,
        cache: MarketDataCache | None = None,
        cache_ttl: timedelta = timedelta(hours=6),
        volume_lookback: int = 20,
    ) -> None:
        if volume_lookback < 1:
            raise ValueError("volume_lookback must be a positive number of sessions.")
        if cache_ttl < timedelta(0):
            raise ValueError("cache_ttl cannot be negative.")
        self.fetcher = fetcher
        self.cache = cache
        self.cache_ttl = cache_ttl
        self.volume_lookback = volume_lookback

    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        *,
        fetched_at: datetime | None = None,
    ) -> MarketDataResult:
        symbol = normalize_nse_ticker(ticker)
        if start > end:
            raise ValueError("start must be on or before end.")
        fetched_at = fetched_at or datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        warmup_start = start - timedelta(days=max(self.volume_lookback * 3, 60))
        exchange_now = fetched_at.astimezone(EXCHANGE_TIMEZONE)
        latest_completed_date = (
            exchange_now.date()
            if exchange_now.time() >= time(16, 0)
            else exchange_now.date() - timedelta(days=1)
        )
        completed_end = min(end, latest_completed_date)
        if completed_end < start:
            return MarketDataResult(
                ticker=symbol,
                data=pd.DataFrame(),
                source=SOURCE_NAME,
                fetched_at=fetched_at,
                status="no_data",
                error_code="session_not_complete",
                detail="The current NSE session is not complete; no partial daily bar was returned.",
            )
        cached = (
            self.cache.load(symbol, warmup_start, completed_end)
            if self.cache is not None
            else None
        )
        if cached is not None and not cached.empty:
            newest_fetch = cached["fetched_at"].max() if "fetched_at" in cached else None
            if newest_fetch is not None:
                cached_at = pd.Timestamp(newest_fetch)
                if cached_at.tzinfo is None:
                    cached_at = cached_at.tz_localize(timezone.utc)
                if fetched_at - cached_at.to_pydatetime() <= self.cache_ttl:
                    cached_metrics = calculate_market_metrics(
                        cached.drop(columns=["fetched_at"], errors="ignore"),
                        requested_start=pd.Timestamp(start),
                        requested_end=pd.Timestamp(completed_end),
                        volume_lookback=self.volume_lookback,
                    )
                    if cached_metrics.empty:
                        return MarketDataResult(
                            ticker=symbol,
                            data=cached_metrics,
                            source=SOURCE_NAME,
                            fetched_at=cached_at.to_pydatetime(),
                            status="no_data",
                            error_code="no_sessions_in_range",
                            detail="The cache contains no sessions within the requested date range.",
                        )
                    return MarketDataResult(
                        ticker=symbol,
                        data=cached_metrics,
                        source=SOURCE_NAME,
                        fetched_at=cached_at.to_pydatetime(),
                        status="cached",
                    )

        try:
            raw = self.fetcher(symbol, warmup_start, completed_end + timedelta(days=1))
            validated = validate_ohlcv(raw, ticker=symbol)
            validated = validated.loc[validated.index.date <= completed_end].copy()
            full_metrics = calculate_market_metrics(
                validated,
                requested_start=pd.Timestamp(warmup_start),
                requested_end=pd.Timestamp(completed_end),
                volume_lookback=self.volume_lookback,
            )
            metrics = full_metrics.loc[
                (full_metrics.index >= pd.Timestamp(start))
                & (full_metrics.index <= pd.Timestamp(completed_end))
            ].copy()
        except DataValidationError:
            if self.cache is not None:
                self.cache.mark_attempt(symbol, "failed", "invalid_source_data", fetched_at)
            raise
        except Exception as error:
            logger.warning(
                "Market source failed for ticker=%s error_type=%s",
                symbol,
                type(error).__name__,
            )
            result = MarketDataResult(
                ticker=symbol,
                data=pd.DataFrame(),
                source=SOURCE_NAME,
                fetched_at=fetched_at,
                status="failed",
                error_code="source_unavailable",
                detail=type(error).__name__,
            )
            if self.cache is not None:
                self.cache.mark_attempt(symbol, "failed", result.error_code, fetched_at)
            return result

        if metrics.empty:
            session_incomplete = completed_end < start or end > latest_completed_date
            result = MarketDataResult(
                ticker=symbol,
                data=metrics,
                source=SOURCE_NAME,
                fetched_at=fetched_at,
                status="no_data",
                error_code=(
                    "session_not_complete" if session_incomplete else "no_sessions_in_range"
                ),
                detail=(
                    "The current NSE session is not complete; no partial daily bar was returned."
                    if session_incomplete
                    else "The source returned no sessions within the requested date range."
                ),
            )
            if self.cache is not None:
                self.cache.mark_attempt(symbol, "no_data", result.error_code, fetched_at)
            return result

        cache_data = full_metrics.copy()
        cache_data["source"] = SOURCE_NAME
        cache_data["fetched_at"] = fetched_at
        result_data = metrics.copy()
        result_data["source"] = SOURCE_NAME
        result_data["fetched_at"] = fetched_at
        result = MarketDataResult(
            ticker=symbol,
            data=result_data,
            source=SOURCE_NAME,
            fetched_at=fetched_at,
            status="fetched",
        )
        if self.cache is not None:
            self.cache.store(symbol, warmup_start, completed_end, cache_data)
            self.cache.mark_attempt(symbol, "success", None, fetched_at)
        return result

    def fetch_many(
        self, tickers: tuple[str, ...] | list[str], start: date, end: date
    ) -> dict[str, MarketDataResult]:
        results: dict[str, MarketDataResult] = {}
        for ticker in tickers:
            try:
                normalized = normalize_nse_ticker(ticker)
                results[normalized] = self.fetch(normalized, start, end)
            except (DataValidationError, ValueError) as error:
                logger.warning(
                    "Market request rejected for ticker=%s error_type=%s",
                    ticker,
                    type(error).__name__,
                )
                results[ticker] = MarketDataResult(
                    ticker=ticker,
                    data=pd.DataFrame(),
                    source=SOURCE_NAME,
                    fetched_at=datetime.now(timezone.utc),
                    status="failed",
                    error_code="invalid_request",
                    detail=str(error),
                )
        return results
