from __future__ import annotations

import re

import pandas as pd


_TICKER_PATTERN = re.compile(r"^[A-Z0-9&-]{1,32}$")


class DataValidationError(ValueError):
    """Raised when source data cannot safely be normalized."""


def normalize_nse_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.endswith(".NS"):
        normalized = normalized[:-3]
    if not _TICKER_PATTERN.fullmatch(normalized):
        raise DataValidationError("Ticker must be a supported NSE symbol.")
    return normalized


def _column_map(columns: pd.Index) -> dict[str, object]:
    return {str(column).strip().casefold(): column for column in columns}


def validate_ohlcv(frame: pd.DataFrame, *, ticker: str) -> pd.DataFrame:
    """Normalize yfinance EOD bars, rejecting invalid prices and removing incomplete rows."""
    if frame.empty:
        raise DataValidationError(f"No daily market data returned for {ticker}.")

    column_map = _column_map(frame.columns)
    required = ("open", "high", "low", "close", "volume")
    missing = [column for column in required if column not in column_map]
    if missing:
        raise DataValidationError(f"Market data is missing columns: {', '.join(missing)}.")

    data = pd.DataFrame(index=frame.index.copy())
    for column in required:
        data[column] = pd.to_numeric(frame[column_map[column]], errors="coerce")

    adjusted_column = column_map.get("adj close")
    if adjusted_column is None:
        adjusted_column = column_map.get("adjusted close")
    data["adjusted_close"] = (
        pd.to_numeric(frame[adjusted_column], errors="coerce")
        if adjusted_column is not None
        else float("nan")
    )

    try:
        dates = pd.DatetimeIndex(pd.to_datetime(data.index, errors="raise"))
    except (TypeError, ValueError) as error:
        raise DataValidationError("Market data contains invalid session dates.") from error
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    data.index = dates.normalize()
    data.index.name = "market_date"

    if data.isin([float("inf"), float("-inf")]).any().any():
        raise DataValidationError(f"Market data contains non-finite values for {ticker}.")
    data = data.dropna(subset=list(required))
    if data.empty:
        raise DataValidationError(f"No complete OHLCV rows returned for {ticker}.")

    if (data[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataValidationError(f"Market prices must be greater than zero for {ticker}.")
    if (data["volume"] < 0).any():
        raise DataValidationError(f"Market volume cannot be negative for {ticker}.")
    adjusted = data["adjusted_close"].dropna()
    if (adjusted <= 0).any():
        raise DataValidationError(f"Adjusted prices must be greater than zero for {ticker}.")
    fractional_volume = data["volume"] % 1 != 0
    if fractional_volume.any():
        raise DataValidationError(f"Market volume must be an integer for {ticker}.")

    max_price = data[["open", "low", "close"]].max(axis=1)
    min_price = data[["open", "high", "close"]].min(axis=1)
    if (data["high"] < max_price).any() or (data["low"] > min_price).any():
        raise DataValidationError(f"OHLC price bounds are inconsistent for {ticker}.")

    data = data.sort_index(kind="stable")
    data = data.loc[~data.index.duplicated(keep="last")]
    data["volume"] = data["volume"].astype("int64")
    return data


def calculate_market_metrics(
    frame: pd.DataFrame,
    *,
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp,
    volume_lookback: int = 20,
) -> pd.DataFrame:
    """Calculate EOD metrics; volume ratio uses the preceding completed sessions."""
    if volume_lookback < 1:
        raise ValueError("volume_lookback must be a positive number of sessions.")

    data = frame.copy().sort_index()
    data["daily_change"] = data["close"].diff()
    data["daily_change_pct"] = data["close"].pct_change(fill_method=None) * 100
    data["average_volume_20"] = (
        data["volume"].shift(1).rolling(window=volume_lookback, min_periods=volume_lookback).mean()
    )
    data["volume_ratio"] = data["volume"] / data["average_volume_20"].where(
        data["average_volume_20"] > 0
    )

    return_basis = data["adjusted_close"].where(data["adjusted_close"].notna(), data["close"])
    first_selected = return_basis.loc[
        (return_basis.index >= requested_start) & (return_basis.index <= requested_end)
    ]
    if first_selected.empty:
        data["historical_return_pct"] = float("nan")
    else:
        base_value = first_selected.iloc[0]
        data["historical_return_pct"] = (return_basis / base_value - 1) * 100

    return data.loc[(data.index >= requested_start) & (data.index <= requested_end)].copy()
