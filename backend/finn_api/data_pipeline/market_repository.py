from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from finn_api.data_pipeline.market_data import MarketDataCache
from finn_api.db.models import CompanyAlias, MarketDaily, SourceSyncState


class MarketCompanyMappingError(ValueError):
    """Raised when an NSE symbol has not been mapped to a canonical company."""


class SQLAlchemyMarketRepository(MarketDataCache):
    """PostgreSQL-backed EOD cache keyed by company, exchange, session, and source."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _company_id(self, ticker: str):
        alias = self.session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == "NSE",
                CompanyAlias.normalized_symbol == ticker,
            )
        )
        return alias.company_id if alias is not None else None

    def load(self, ticker: str, start: date, end: date) -> pd.DataFrame | None:
        company_id = self._company_id(ticker)
        if company_id is None:
            return None

        rows = self.session.scalars(
            select(MarketDaily)
            .where(
                MarketDaily.company_id == company_id,
                MarketDaily.exchange == "NSE",
                MarketDaily.market_date >= start,
                MarketDaily.market_date <= end,
                MarketDaily.source == "yfinance",
            )
            .order_by(MarketDaily.market_date)
        ).all()
        if not rows:
            return None

        data = pd.DataFrame(
            [
                {
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "adjusted_close": row.adjusted_close,
                    "volume": row.volume,
                    "daily_change": row.daily_change,
                    "daily_change_pct": row.daily_change_pct,
                    "average_volume_20": row.average_volume_20,
                    "volume_ratio": row.volume_ratio,
                    "fetched_at": row.fetched_at,
                    "source": row.source,
                }
                for row in rows
            ],
            index=pd.DatetimeIndex([row.market_date for row in rows], name="market_date"),
        )
        return data

    def store(self, ticker: str, start: date, end: date, frame: pd.DataFrame) -> None:
        del start, end
        company_id = self._company_id(ticker)
        if company_id is None:
            raise MarketCompanyMappingError(f"No NSE company alias is registered for {ticker}.")

        rows: list[dict[str, object]] = []
        for market_date, values in frame.iterrows():
            rows.append(
                {
                    "id": uuid4(),
                    "company_id": company_id,
                    "exchange": "NSE",
                    "market_date": market_date.date(),
                    "open": _decimal_or_none(values.get("open")),
                    "high": _decimal_or_none(values.get("high")),
                    "low": _decimal_or_none(values.get("low")),
                    "close": _decimal_or_none(values.get("close")),
                    "adjusted_close": _decimal_or_none(values.get("adjusted_close")),
                    "volume": int(values["volume"]),
                    "daily_change": _decimal_or_none(values.get("daily_change")),
                    "daily_change_pct": _decimal_or_none(values.get("daily_change_pct")),
                    "average_volume_20": _decimal_or_none(values.get("average_volume_20")),
                    "volume_ratio": _decimal_or_none(values.get("volume_ratio")),
                    "currency": "INR",
                    "adjusted": pd.notna(values.get("adjusted_close")),
                    "source": "yfinance",
                    "fetched_at": values["fetched_at"].to_pydatetime()
                    if isinstance(values["fetched_at"], pd.Timestamp)
                    else values["fetched_at"],
                }
            )

        statement = insert(MarketDaily).values(rows)
        update_columns = (
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
            "daily_change",
            "daily_change_pct",
            "average_volume_20",
            "volume_ratio",
            "adjusted",
            "fetched_at",
        )
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    MarketDaily.company_id,
                    MarketDaily.exchange,
                    MarketDaily.market_date,
                    MarketDaily.source,
                ],
                set_={column: getattr(statement.excluded, column) for column in update_columns},
            )
        )
        self._mark_attempt(ticker, "success", None, frame["fetched_at"].iloc[-1])
        self.session.commit()

    def mark_attempt(
        self, ticker: str, status: str, error_code: str | None, attempted_at: datetime
    ) -> None:
        self._mark_attempt(ticker, status, error_code, attempted_at)
        self.session.commit()

    def _mark_attempt(
        self, ticker: str, status: str, error_code: str | None, attempted_at: datetime
    ) -> None:
        scope_key = f"market:NSE:{ticker}"
        state = self.session.scalar(
            select(SourceSyncState).where(
                SourceSyncState.source == "yfinance",
                SourceSyncState.scope_key == scope_key,
            )
        )
        if state is None:
            state = SourceSyncState(
                source="yfinance",
                scope_key=scope_key,
                status=status,
            )
            self.session.add(state)
        state.last_attempt_at = attempted_at
        state.status = status
        state.last_error_code = error_code
        if status == "success":
            state.last_success_at = attempted_at


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value))
