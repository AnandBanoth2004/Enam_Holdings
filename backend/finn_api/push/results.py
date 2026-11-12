from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.models import (
    Company,
    CompanyAlias,
    Document,
    FinancialMetric,
    FinancialStatementPeriod,
)

METRIC_KEYS = ("revenue", "ebitda", "pbt", "pat")
UNIT_FACTORS = {
    "unit": Decimal(1),
    "units": Decimal(1),
    "rupee": Decimal(1),
    "rupees": Decimal(1),
    "thousand": Decimal(1_000),
    "thousands": Decimal(1_000),
    "lakh": Decimal(100_000),
    "lakhs": Decimal(100_000),
    "lac": Decimal(100_000),
    "lacs": Decimal(100_000),
    "million": Decimal(1_000_000),
    "millions": Decimal(1_000_000),
    "mn": Decimal(1_000_000),
    "crore": Decimal(10_000_000),
    "crores": Decimal(10_000_000),
    "cr": Decimal(10_000_000),
    "billion": Decimal(1_000_000_000),
    "billions": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
}


@dataclass(frozen=True)
class PeriodValue:
    value: Decimal | None
    period_label: str | None
    period_end: date | None
    currency: str | None
    unit_scale: str | None
    reporting_basis: str | None
    source_url: str | None
    is_synthetic: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class MetricComparison:
    metric_key: str
    current: PeriodValue
    qoq: PeriodValue
    yoy: PeriodValue
    qoq_absolute_change: Decimal | None
    qoq_percent_change: Decimal | None
    qoq_change_note: str | None
    yoy_absolute_change: Decimal | None
    yoy_percent_change: Decimal | None
    yoy_change_note: str | None


@dataclass(frozen=True)
class ResultsComparison:
    ticker: str
    company_name: str
    reporting_basis: str
    currency: str
    unit_scale: str
    current_period: str
    metrics: tuple[MetricComparison, ...]


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _normalize_unit(unit: str) -> str:
    normalized = unit.strip().casefold().replace("_", " ")
    if normalized not in UNIT_FACTORS:
        raise ValueError(f"Unsupported financial unit scale: {unit}")
    return normalized


def _to_current_unit(value: Decimal, source_unit: str, target_unit: str) -> Decimal:
    return value * UNIT_FACTORS[_normalize_unit(source_unit)] / UNIT_FACTORS[_normalize_unit(target_unit)]


def _load_period_values(
    session: Session,
    period: FinancialStatementPeriod | None,
    *,
    currency: str,
    unit_scale: str,
) -> dict[str, PeriodValue]:
    if period is None:
        return {
            key: PeriodValue(
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                "No matching reported financial period is available.",
            )
            for key in METRIC_KEYS
        }

    document = session.get(Document, period.document_id)
    metrics = session.scalars(
        select(FinancialMetric).where(
            FinancialMetric.statement_period_id == period.id,
            FinancialMetric.reporting_basis == period.reporting_basis,
        )
    ).all()
    by_key: dict[str, PeriodValue] = {}
    for metric in metrics:
        if metric.metric_key not in METRIC_KEYS:
            continue
        if metric.currency.upper() != currency.upper():
            by_key[metric.metric_key] = PeriodValue(
                None,
                period.period_label,
                period.period_end,
                metric.currency,
                metric.unit_scale,
                period.reporting_basis,
                document.source_url if document else None,
                bool(period.is_synthetic or metric.is_synthetic),
                f"Currency {metric.currency} does not match current-period currency {currency}.",
            )
            continue
        try:
            normalized = _to_current_unit(
                Decimal(metric.reported_value), metric.unit_scale, unit_scale
            )
        except ValueError as error:
            by_key[metric.metric_key] = PeriodValue(
                None,
                period.period_label,
                period.period_end,
                metric.currency,
                metric.unit_scale,
                period.reporting_basis,
                document.source_url if document else None,
                bool(period.is_synthetic or metric.is_synthetic),
                str(error),
            )
            continue
        by_key[metric.metric_key] = PeriodValue(
            normalized,
            period.period_label,
            period.period_end,
            currency,
            unit_scale,
            period.reporting_basis,
            document.source_url if document else None,
            bool(period.is_synthetic or metric.is_synthetic),
        )

    for key in METRIC_KEYS:
        by_key.setdefault(
            key,
            PeriodValue(
                None,
                period.period_label,
                period.period_end,
                currency,
                unit_scale,
                period.reporting_basis,
                document.source_url if document else None,
                period.is_synthetic,
                "This metric is absent from the source period; no value was inferred.",
            ),
        )
    return by_key


def _compare(
    current: PeriodValue, comparison: PeriodValue
) -> tuple[Decimal | None, Decimal | None, str | None]:
    if current.value is None:
        return None, None, current.reason or "Current-period value is unavailable."
    if comparison.value is None:
        return None, None, comparison.reason or "Comparison value is unavailable."
    difference = current.value - comparison.value
    if comparison.value <= 0:
        return (
            difference,
            None,
            "Absolute movement is shown; percentage change is not reported for a zero or negative comparison base.",
        )
    return difference, difference / comparison.value * Decimal(100), None


def compare_company_results(
    session: Session,
    ticker: str,
    *,
    reporting_basis: str | None = None,
) -> ResultsComparison:
    normalized_ticker = ticker.strip().upper().removesuffix(".NS")
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == normalized_ticker,
        )
    )
    if alias is None:
        raise LookupError(f"No NSE company mapping exists for ticker {normalized_ticker}.")

    periods_query = select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.company_id == alias.company_id,
        FinancialStatementPeriod.period_type == "quarter",
    )
    if reporting_basis:
        periods_query = periods_query.where(
            FinancialStatementPeriod.reporting_basis == reporting_basis
        )
    periods = session.scalars(
        periods_query.order_by(FinancialStatementPeriod.period_end.desc())
    ).all()
    if not periods:
        raise LookupError(f"No reported quarterly data is available for {normalized_ticker}.")

    current_period = periods[0]
    current_values = _load_period_values(
        session,
        current_period,
        currency=current_period.currency,
        unit_scale=current_period.unit_scale,
    )
    periods_by_end = {
        period.period_end: period
        for period in periods
        if period.reporting_basis == current_period.reporting_basis
        and period.currency.upper() == current_period.currency.upper()
    }
    qoq_period = periods_by_end.get(_shift_months(current_period.period_end, -3))
    yoy_period = periods_by_end.get(_shift_months(current_period.period_end, -12))
    qoq_values = _load_period_values(
        session,
        qoq_period,
        currency=current_period.currency,
        unit_scale=current_period.unit_scale,
    )
    yoy_values = _load_period_values(
        session,
        yoy_period,
        currency=current_period.currency,
        unit_scale=current_period.unit_scale,
    )

    comparisons: list[MetricComparison] = []
    for key in METRIC_KEYS:
        current = current_values[key]
        qoq = qoq_values[key]
        yoy = yoy_values[key]
        qoq_absolute, qoq_percent, qoq_note = _compare(current, qoq)
        yoy_absolute, yoy_percent, yoy_note = _compare(current, yoy)
        if qoq_period is None:
            qoq = PeriodValue(
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                "Immediately preceding quarter is missing; no other period was substituted.",
            )
            qoq_absolute, qoq_percent, qoq_note = _compare(current, qoq)
        if yoy_period is None:
            yoy = PeriodValue(
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                "Same quarter one year earlier is missing; no other period was substituted.",
            )
            yoy_absolute, yoy_percent, yoy_note = _compare(current, yoy)
        comparisons.append(
            MetricComparison(
                key,
                current,
                qoq,
                yoy,
                qoq_absolute,
                qoq_percent,
                qoq_note,
                yoy_absolute,
                yoy_percent,
                yoy_note,
            )
        )

    company = session.get(Company, alias.company_id)
    if company is None:
        raise LookupError(f"Company mapping for {normalized_ticker} is invalid.")
    return ResultsComparison(
        normalized_ticker,
        company.display_name,
        current_period.reporting_basis,
        current_period.currency,
        current_period.unit_scale,
        current_period.period_label,
        tuple(comparisons),
    )


@dataclass(frozen=True)
class ExtractedResultMetric:
    metric_key: Literal["revenue", "ebitda", "pbt", "pat"]
    value: Decimal
    currency: str
    unit_scale: str
    source_excerpt: str


_METRIC_LABELS = {
    "revenue": re.compile(r"\b(revenue(?: from operations)?|sales)\b", re.IGNORECASE),
    "ebitda": re.compile(r"\b(ebitda|earnings before interest,?\s*tax,?\s*depreciation(?: and| &)? amorti[sz]ation)\b", re.IGNORECASE),
    "pbt": re.compile(r"\b(pbt|profit before tax|profit before taxation)\b", re.IGNORECASE),
    "pat": re.compile(r"\b(pat|profit after tax|net profit)\b", re.IGNORECASE),
}
_NUMBER_AFTER_LABEL = re.compile(
    r"^\s*[:=–-]?\s*(?:INR|Rs\.?|₹)?\s*"
    r"(?P<value>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*"
    r"(?P<unit>crores?|cr\b|lakhs?|lacs?|million|mn\b|billions?|bn\b)?",
    re.IGNORECASE,
)


def extract_result_metrics(
    text: str,
    *,
    currency: str = "INR",
    default_unit_scale: str | None = None,
) -> dict[str, ExtractedResultMetric]:
    """Parse explicit labeled figures from text; ambiguous/missing values are omitted."""
    extracted: dict[str, ExtractedResultMetric] = {}
    for metric_key, label_pattern in _METRIC_LABELS.items():
        candidates: list[ExtractedResultMetric] = []
        for label in label_pattern.finditer(text):
            excerpt = text[label.start() : min(len(text), label.end() + 80)]
            value_match = _NUMBER_AFTER_LABEL.match(text[label.end() :])
            if value_match is None:
                continue
            unit = value_match.group("unit")
            if unit is None and default_unit_scale is None:
                continue
            raw_value = value_match.group("value").replace(",", "")
            negative_parentheses = raw_value.startswith("(") and raw_value.endswith(")")
            raw_value = raw_value.strip("()")
            value = Decimal(raw_value)
            if negative_parentheses:
                value = -value
            candidates.append(
                ExtractedResultMetric(
                    metric_key=cast(Literal["revenue", "ebitda", "pbt", "pat"], metric_key),
                    value=value,
                    currency=currency.upper(),
                    unit_scale=unit or default_unit_scale or "unit",
                    source_excerpt=excerpt.strip(),
                )
            )
        if len(candidates) == 1:
            extracted[metric_key] = candidates[0]
    return extracted
