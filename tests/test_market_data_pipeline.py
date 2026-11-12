from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from finn_api.data_pipeline.market_data import InMemoryMarketCache, MarketDataService
from finn_api.data_pipeline.validation import (
    DataValidationError,
    calculate_market_metrics,
    normalize_nse_ticker,
    validate_ohlcv,
)


def sample_frame(days: int = 35) -> pd.DataFrame:
    dates = pd.bdate_range("2026-09-01", periods=days, tz="Asia/Kolkata")
    values = range(100, 100 + days)
    return pd.DataFrame(
        {
            "Open": [value - 0.5 for value in values],
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": list(values),
            "Adj Close": [value * 0.99 for value in values],
            "Volume": [1000 + value for value in values],
        },
        index=dates,
    )


def test_ticker_normalization_and_rejection() -> None:
    assert normalize_nse_ticker(" reliance.ns ") == "RELIANCE"
    with pytest.raises(DataValidationError):
        normalize_nse_ticker("UNKNOWN TICKER")


def test_validation_handles_missing_adjusted_close_and_duplicate_dates() -> None:
    frame = sample_frame(3).drop(columns=["Adj Close"])
    frame = pd.concat([frame, frame.iloc[[-1]].assign(Close=999)])
    frame.iloc[-1, frame.columns.get_loc("High")] = 1000

    actual = validate_ohlcv(frame, ticker="TEST")

    assert len(actual) == 3
    assert actual["close"].iloc[-1] == 999
    assert actual["adjusted_close"].isna().all()
    assert actual["volume"].dtype == "int64"


def test_validation_rejects_bad_ohlc_bounds_and_negative_volume() -> None:
    invalid_bounds = sample_frame(2)
    invalid_bounds.iloc[0, invalid_bounds.columns.get_loc("High")] = 1
    with pytest.raises(DataValidationError, match="bounds"):
        validate_ohlcv(invalid_bounds, ticker="TEST")

    invalid_volume = sample_frame(2)
    invalid_volume.iloc[0, invalid_volume.columns.get_loc("Volume")] = -1
    with pytest.raises(DataValidationError, match="negative"):
        validate_ohlcv(invalid_volume, ticker="TEST")


def test_metrics_use_prior_twenty_sessions_and_adjusted_historical_return() -> None:
    validated = validate_ohlcv(sample_frame(), ticker="TEST")
    start = validated.index[25].date()
    end = validated.index[-1].date()

    result = calculate_market_metrics(
        validated,
        requested_start=pd.Timestamp(start),
        requested_end=pd.Timestamp(end),
    )

    first = result.iloc[0]
    prior_volumes = validated["volume"].iloc[5:25]
    assert first["average_volume_20"] == pytest.approx(prior_volumes.mean())
    assert first["volume_ratio"] == pytest.approx(first["volume"] / prior_volumes.mean())
    assert first["daily_change"] == pytest.approx(1)
    assert first["daily_change_pct"] == pytest.approx((125 / 124 - 1) * 100)
    assert first["historical_return_pct"] == pytest.approx(0)
    assert result.iloc[-1]["historical_return_pct"] > 0


def test_market_service_fetch_is_eod_only_inclusive_and_cached() -> None:
    raw = sample_frame()
    start = raw.index[25].date()
    end = raw.index[-1].date()
    calls: list[tuple[str, date, date]] = []

    def fetcher(symbol: str, fetch_start: date, fetch_end: date) -> pd.DataFrame:
        calls.append((symbol, fetch_start, fetch_end))
        return raw

    cache = InMemoryMarketCache()
    service = MarketDataService(fetcher=fetcher, cache=cache)
    fetched = service.fetch("TEST.NS", start, end)
    cached = service.fetch("TEST", start, end)

    assert fetched.status == "fetched"
    assert fetched.source == "yfinance"
    assert fetched.data.index.min().date() == start
    assert fetched.data.index.max().date() == end
    assert calls[0][0] == "TEST"
    assert calls[0][2] == end + timedelta(days=1)
    assert cached.status == "cached"
    assert len(calls) == 1


def test_market_source_failures_are_reported_per_ticker() -> None:
    def failing_fetcher(symbol: str, start: date, end: date) -> pd.DataFrame:
        raise TimeoutError("provider timeout")

    result = MarketDataService(fetcher=failing_fetcher).fetch_many(
        ["TEST", "bad ticker"], date(2026, 1, 1), date(2026, 1, 5)
    )

    assert result["TEST"].status == "failed"
    assert result["TEST"].error_code == "source_unavailable"
    assert result["bad ticker"].status == "failed"
    assert result["bad ticker"].error_code == "invalid_request"


def test_current_nse_session_is_not_exposed_as_eod_before_close() -> None:
    dates = pd.DatetimeIndex(["2026-11-10", "2026-11-11"], tz="Asia/Kolkata")
    raw = pd.DataFrame(
        {
            "Open": [100, 101],
            "High": [102, 103],
            "Low": [99, 100],
            "Close": [101, 102],
            "Volume": [1000, 1100],
        },
        index=dates,
    )
    calls: list[date] = []

    def fetcher(symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(end)
        return raw

    service = MarketDataService(fetcher=fetcher)
    before_close = service.fetch(
        "TEST",
        date(2026, 11, 11),
        date(2026, 11, 11),
        fetched_at=datetime(2026, 11, 11, 12, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    after_close = service.fetch(
        "TEST",
        date(2026, 11, 11),
        date(2026, 11, 11),
        fetched_at=datetime(2026, 11, 11, 17, tzinfo=ZoneInfo("Asia/Kolkata")),
    )

    assert before_close.status == "no_data"
    assert before_close.error_code == "session_not_complete"
    assert not before_close.is_live
    assert before_close.data_frequency == "daily_eod"
    assert len(calls) == 1
    assert after_close.status == "fetched"
    assert after_close.data.index.min().date() == date(2026, 11, 11)
