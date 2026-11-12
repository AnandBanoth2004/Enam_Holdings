from __future__ import annotations

import calendar
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.models import (
    Company,
    CompanyAlias,
    Document,
    DocumentChunk,
    FinancialMetric,
    FinancialStatementPeriod,
    GuidanceAssessment,
    ManagementGuidance,
)

_UNIT_FACTORS = {
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
_GUIDANCE_WORDS = re.compile(
    r"\b(?:guidance|guided|expect(?:ed|s)?|target(?:ed|s)?|aim(?:s|ing)?|"
    r"outlook|plan(?:s|ned)?|forecast|project(?:s|ed)?)\b",
    re.I,
)
_COMMENTARY_WORDS = re.compile(
    r"\b(?:guidance|guided|expect(?:ed|s)?|target(?:ed|s)?|aim(?:s|ing)?|"
    r"outlook|plan(?:s|ned)?|forecast|project(?:s|ed)?|growth|margin|"
    r"capex|capital expenditure|demand|pricing|volume|cost|cash flow)\b",
    re.I,
)
_NUMBER = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?")
_PERCENT = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*%")
_PERCENT_RANGE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<high>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_MONEY_TARGET = re.compile(
    r"(?:(?:INR|Rs\.?|₹)\s*)?"
    r"(?P<low>-?\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(?:-|–|to)\s*(?P<high>-?\d[\d,]*(?:\.\d+)?))?"
    r"\s*(?P<unit>crores?|cr\b|lakhs?|lacs?|millions?|mn\b|billions?|bn\b|thousands?)",
    re.I,
)
_PERIOD_QUARTER = re.compile(
    r"\bQ([1-4])\s*(?:FY|of\s+FY)\s*['’]?(20\d{2}|\d{2})\b", re.I
)
_PERIOD_YEAR = re.compile(r"\bFY\s*['’]?(20\d{2})\s*[-–/]\s*(\d{2,4})\b", re.I)
_YEAR_SINGLE = re.compile(r"\bFY\s*['’]?(20\d{2}|\d{2})\b", re.I)


@dataclass(frozen=True)
class _StoredMetric:
    value: Decimal
    metric: FinancialMetric
    document: Document


@dataclass(frozen=True)
class _Statement:
    period: FinancialStatementPeriod
    document: Document
    metrics: dict[str, _StoredMetric]


@dataclass(frozen=True)
class _GuidanceCandidate:
    document: Document
    chunk: DocumentChunk
    statement: str
    metric_key: str
    target_low: Decimal
    target_high: Decimal
    currency: str | None
    unit_scale: str
    target_start: date | None
    target_end: date | None
    target_label: str | None


def _scale(value: Decimal, source: str, target: str) -> Decimal:
    source_key, target_key = source.casefold().strip(), target.casefold().strip()
    if source_key not in _UNIT_FACTORS or target_key not in _UNIT_FACTORS:
        raise ValueError(f"Unsupported financial unit scale: {source} or {target}")
    return value * _UNIT_FACTORS[source_key] / _UNIT_FACTORS[target_key]


def _percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous <= 0:
        return None
    return (current - previous) / previous * Decimal(100)


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _period_from_text(
    text: str,
) -> tuple[str | None, date | None, date | None]:
    quarter = _PERIOD_QUARTER.search(text)
    year_range = _PERIOD_YEAR.search(text)
    if year_range:
        start_year = int(year_range.group(1))
        end_part = year_range.group(2)
        end_year = int(f"20{end_part}") if len(end_part) == 2 else int(end_part)
        return (
            f"FY{start_year}-{str(end_year)[-2:]}",
            date(start_year, 4, 1),
            date(end_year, 3, 31),
        )
    if quarter:
        quarter_number = int(quarter.group(1))
        raw_year = int(quarter.group(2))
        end_year = raw_year if raw_year >= 100 else 2000 + raw_year
        start_year = end_year - 1
        bounds = {
            1: (date(start_year, 4, 1), date(start_year, 6, 30)),
            2: (date(start_year, 7, 1), date(start_year, 9, 30)),
            3: (date(start_year, 10, 1), date(start_year, 12, 31)),
            4: (date(end_year, 1, 1), date(end_year, 3, 31)),
        }
        period_start, period_end = bounds[quarter_number]
        return f"Q{quarter_number} FY{end_year}", period_start, period_end
    single = _YEAR_SINGLE.search(text)
    if single:
        raw_year = int(single.group(1))
        end_year = raw_year if raw_year >= 100 else 2000 + raw_year
        return (
            f"FY{end_year - 1}-{str(end_year)[-2:]}",
            date(end_year - 1, 4, 1),
            date(end_year, 3, 31),
        )
    return None, None, None


def _citation(
    document: Document,
    *,
    page_number: int | None,
    quote: str | None,
    chunk_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "document_name": document.title,
        "document_type": document.document_type,
        "reporting_period": document.period_label,
        "page_number": page_number,
        "source_url": document.source_url,
        "quote": quote,
        "chunk_id": chunk_id,
        "is_synthetic": bool(document.synthetic),
    }


def _load_statements(
    session: Session,
    company_id: UUID,
    reporting_basis: str,
) -> list[_Statement]:
    rows = session.execute(
        select(FinancialStatementPeriod, Document)
        .join(Document, Document.id == FinancialStatementPeriod.document_id)
        .where(
            FinancialStatementPeriod.company_id == company_id,
            FinancialStatementPeriod.reporting_basis == reporting_basis,
            FinancialStatementPeriod.is_synthetic.is_(False),
            Document.is_primary_source.is_(True),
            Document.synthetic.is_(False),
            Document.ingestion_status.in_(("extracted", "embedded")),
            Document.document_type.in_(
                ("annual_report", "quarterly_result", "earnings_call_transcript", "investor_presentation")
            ),
        )
        .order_by(FinancialStatementPeriod.period_end.desc())
    ).all()
    statements: list[_Statement] = []
    for period, document in rows:
        metrics = session.scalars(
            select(FinancialMetric).where(
                FinancialMetric.statement_period_id == period.id,
                FinancialMetric.reporting_basis == reporting_basis,
                FinancialMetric.is_synthetic.is_(False),
            )
        ).all()
        by_key: dict[str, _StoredMetric] = {}
        for metric in metrics:
            if metric.currency.upper() != period.currency.upper():
                continue
            try:
                value = _scale(
                    Decimal(metric.reported_value),
                    metric.unit_scale,
                    period.unit_scale,
                )
            except ValueError:
                continue
            by_key[metric.metric_key] = _StoredMetric(value, metric, document)
        statements.append(_Statement(period, document, by_key))

    unique: dict[tuple[date, str, str], _Statement] = {}
    for statement in statements:
        key = (
            statement.period.period_end,
            statement.period.period_type,
            statement.period.reporting_basis,
        )
        previous = unique.get(key)
        if previous is None or (
            statement.document.fetched_at,
            str(statement.document.id),
        ) > (previous.document.fetched_at, str(previous.document.id)):
            unique[key] = statement
    return sorted(
        unique.values(),
        key=lambda item: (item.period.period_end, item.period.period_type),
        reverse=True,
    )


def _metric_fact(statement: _Statement, key: str) -> dict[str, Any] | None:
    item = statement.metrics.get(key)
    if item is None:
        return None
    metric = item.metric
    formatted = format(Decimal(metric.reported_value), "f")
    text = (
        f"{key.replace('_', ' ').title()}: {formatted} "
        f"{metric.currency} {metric.unit_scale} for {statement.period.period_label} "
        f"({statement.period.reporting_basis})."
    )
    return {
        "text": text,
        "claim_type": "reported_fact",
        "value": formatted,
        "metric_key": key,
        "period_label": statement.period.period_label,
        "currency": metric.currency,
        "unit_scale": metric.unit_scale,
        "reporting_basis": statement.period.reporting_basis,
        "citations": [
            _citation(
                item.document,
                page_number=metric.source_page,
                quote=metric.source_excerpt,
            )
        ],
    }


def _calculation(
    text: str,
    citations: Iterable[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "text": text,
        "claim_type": "calculation",
        "citations": list(citations),
        **extra,
    }


def _section_status(
    facts: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    interpretations: list[dict[str, Any]],
) -> str:
    total = len(facts) + len(calculations) + len(interpretations)
    return "ready" if total >= 2 else "partial" if total else "unavailable"


def _source_chunks(
    session: Session,
    company_id: UUID,
    document_types: tuple[str, ...],
    *,
    limit: int = 1200,
) -> list[tuple[DocumentChunk, Document]]:
    return session.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.company_id == company_id,
            Document.document_type.in_(document_types),
            Document.is_primary_source.is_(True),
            Document.synthetic.is_(False),
            DocumentChunk.synthetic.is_(False),
            Document.ingestion_status.in_(("extracted", "embedded")),
        )
        .order_by(Document.period_end.desc(), DocumentChunk.chunk_index)
        .limit(limit)
    ).all()


def _business_snapshot(
    chunks: list[tuple[DocumentChunk, Document]],
) -> dict[str, Any]:
    terms = re.compile(
        r"\b(?:business overview|business model|segments?|products?|services?|"
        r"revenue mix|geographic|operations)\b",
        re.I,
    )
    ranked = sorted(
        chunks,
        key=lambda pair: (
            -len(terms.findall(f"{pair[0].section or ''} {pair[0].text}")),
            -len(pair[0].text),
            str(pair[0].id),
        ),
    )
    facts: list[dict[str, Any]] = []
    for chunk, document in ranked:
        if not terms.search(f"{chunk.section or ''} {chunk.text}"):
            continue
        quote = " ".join(chunk.text.split())[:1200]
        facts.append(
            {
                "text": quote,
                "claim_type": "reported_fact",
                "citations": [
                    _citation(
                        document,
                        page_number=chunk.page_start,
                        quote=quote,
                        chunk_id=chunk.id,
                    )
                ],
            }
        )
        if len(facts) == 4:
            break
    limitations = [] if facts else [
        "No eligible primary-source business overview or segment passages are indexed."
    ]
    return {
        "status": _section_status(facts, [], []),
        "facts": facts,
        "calculations": [],
        "interpretations": [],
        "observations": [],
        "limitations": limitations,
    }


def _financial_snapshot(statements: list[_Statement]) -> dict[str, Any]:
    latest = next((item for item in statements if item.metrics), None)
    if latest is None:
        return {
            "status": "unavailable",
            "facts": [],
            "calculations": [],
            "interpretations": [],
            "observations": [],
            "limitations": ["No comparable, non-synthetic primary-source financial metrics are available."],
        }
    keys = ("revenue", "ebitda", "pbt", "pat", "total_debt", "cash_and_equivalents")
    facts = [fact for key in keys if (fact := _metric_fact(latest, key)) is not None]
    calculations: list[dict[str, Any]] = []
    revenue, ebitda = latest.metrics.get("revenue"), latest.metrics.get("ebitda")
    if revenue and ebitda and revenue.value != 0:
        margin = ebitda.value / revenue.value * Decimal(100)
        citations = [
            _citation(item.document, page_number=item.metric.source_page, quote=item.metric.source_excerpt)
            for item in (revenue, ebitda)
        ]
        calculations.append(
            _calculation(
                f"EBITDA margin = EBITDA / revenue; {margin:.2f}% for {latest.period.period_label}.",
                citations,
                metric_key="ebitda_margin_pct",
                value=f"{margin:.4f}",
                unit_scale="percent",
                period_label=latest.period.period_label,
            )
        )
    limitations = [] if facts else ["Headline financial metrics are absent from the latest indexed period."]
    section_status = _section_status(facts, calculations, [])
    return {
        "status": section_status,
        "facts": facts,
        "calculations": calculations,
        "interpretations": [],
        "observations": [
            {
                "period_label": latest.period.period_label,
                "period_end": latest.period.period_end.isoformat(),
                "period_type": latest.period.period_type,
                "reporting_basis": latest.period.reporting_basis,
                "currency": latest.period.currency,
                "unit_scale": latest.period.unit_scale,
            }
        ],
        "limitations": limitations,
    }


def _trajectory(statements: list[_Statement]) -> dict[str, Any]:
    annual = [item for item in statements if item.period.period_type == "year"]
    annual.sort(key=lambda item: item.period.period_end)
    observations: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []
    limitations: list[str] = []
    for index, current in enumerate(annual):
        values = {
            key: _metric_fact(current, key)
            for key in ("revenue", "ebitda", "pat")
        }
        observations.append(
            {
                "period_label": current.period.period_label,
                "period_end": current.period.period_end.isoformat(),
                "metrics": {
                    key: fact["value"] if fact else None for key, fact in values.items()
                },
                "currency": current.period.currency,
                "unit_scale": current.period.unit_scale,
            }
        )
        facts.extend(fact for fact in values.values() if fact is not None)
        if index == 0:
            continue
        previous = annual[index - 1]
        if (current.period.period_end - previous.period.period_end).days not in range(330, 400):
            limitations.append(
                f"Year-over-year comparison from {previous.period.period_label} to "
                f"{current.period.period_label} is unavailable because the periods are not adjacent annual periods."
            )
            continue
        for key in ("revenue", "ebitda", "pat"):
            now_value, old_value = current.metrics.get(key), previous.metrics.get(key)
            if not now_value or not old_value:
                limitations.append(
                    f"{key.replace('_', ' ').title()} year-over-year comparison is unavailable "
                    f"for {previous.period.period_label} to {current.period.period_label}: "
                    "one or both reported values are missing."
                )
                continue
            if now_value.metric.currency.upper() != old_value.metric.currency.upper():
                limitations.append(
                    f"{key.replace('_', ' ').title()} year-over-year comparison is unavailable "
                    f"for {previous.period.period_label} to {current.period.period_label}: currencies differ."
                )
                continue
            comparable_previous = _scale(
                old_value.value,
                previous.period.unit_scale,
                current.period.unit_scale,
            )
            percent = _percent_change(now_value.value, comparable_previous)
            if percent is None:
                absolute_change = now_value.value - comparable_previous
                citations = [
                    _citation(now_value.document, page_number=now_value.metric.source_page, quote=now_value.metric.source_excerpt),
                    _citation(old_value.document, page_number=old_value.metric.source_page, quote=old_value.metric.source_excerpt),
                ]
                calculations.append(
                    _calculation(
                        f"{key.replace('_', ' ').title()} changed by {absolute_change:f} "
                        f"{current.period.currency} {current.period.unit_scale} from "
                        f"{previous.period.period_label} to {current.period.period_label}; "
                        "percentage change is omitted because the prior-year base is zero or negative.",
                        citations,
                        metric_key=f"{key}_absolute_change",
                        value=f"{absolute_change:f}",
                        currency=current.period.currency,
                        unit_scale=current.period.unit_scale,
                        from_period=previous.period.period_label,
                        to_period=current.period.period_label,
                    )
                )
                limitations.append(
                    f"{key.replace('_', ' ').title()} year-over-year percentage change is not meaningful "
                    f"for {previous.period.period_label} to {current.period.period_label}: "
                    "the prior-year base is zero or negative."
                )
                continue
            citations = [
                _citation(now_value.document, page_number=now_value.metric.source_page, quote=now_value.metric.source_excerpt),
                _citation(old_value.document, page_number=old_value.metric.source_page, quote=old_value.metric.source_excerpt),
            ]
            calculations.append(
                _calculation(
                    f"{key.replace('_', ' ').title()} changed {percent:.2f}% from "
                    f"{previous.period.period_label} to {current.period.period_label}; comparison uses a positive prior-year base.",
                    citations,
                    metric_key=f"{key}_yoy_pct",
                    value=f"{percent:.4f}",
                    from_period=previous.period.period_label,
                    to_period=current.period.period_label,
                )
            )
    if len(annual) == 1:
        limitations.append(
            "Only one annual financial period is available; no year-over-year trajectory can be calculated."
        )
    section_status = _section_status(facts, calculations, [])
    if len(annual) == 1 and facts:
        section_status = "partial"
    return {
        "status": section_status,
        "facts": facts,
        "calculations": calculations,
        "interpretations": [],
        "observations": observations,
        "limitations": limitations
        if observations
        else ["No annual financial periods are available; no trajectory is inferred from quarterly data."],
    }


def _balance_sheet(statements: list[_Statement]) -> dict[str, Any]:
    statement = next(
        (
            item
            for item in statements
            if item.period.period_type == "year"
            and any(
                key in item.metrics
                for key in (
                    "total_debt",
                    "current_borrowings",
                    "non_current_borrowings",
                    "cash_and_equivalents",
                    "total_equity",
                )
            )
        ),
        None,
    )
    if statement is None:
        return {
            "status": "unavailable",
            "facts": [],
            "calculations": [],
            "interpretations": [],
            "observations": [],
            "limitations": ["No annual primary-source balance-sheet figures are available."],
        }
    keys = (
        "total_debt",
        "current_borrowings",
        "non_current_borrowings",
        "cash_and_equivalents",
        "total_equity",
        "total_assets",
        "current_assets",
        "current_liabilities",
        "trade_receivables",
        "inventory",
        "trade_payables",
    )
    facts = [fact for key in keys if (fact := _metric_fact(statement, key)) is not None]
    calculations: list[dict[str, Any]] = []
    debt, cash, equity = (
        statement.metrics.get("total_debt"),
        statement.metrics.get("cash_and_equivalents"),
        statement.metrics.get("total_equity"),
    )
    debt_value = debt.value if debt else None
    debt_citations = (
        [_citation(debt.document, page_number=debt.metric.source_page, quote=debt.metric.source_excerpt)]
        if debt
        else []
    )
    current_borrowings = statement.metrics.get("current_borrowings")
    non_current_borrowings = statement.metrics.get("non_current_borrowings")
    if (
        debt_value is None
        and current_borrowings
        and non_current_borrowings
        and current_borrowings.metric.currency.upper()
        == non_current_borrowings.metric.currency.upper()
    ):
        debt_value = current_borrowings.value + non_current_borrowings.value
        debt_citations = [
            _citation(
                current_borrowings.document,
                page_number=current_borrowings.metric.source_page,
                quote=current_borrowings.metric.source_excerpt,
            ),
            _citation(
                non_current_borrowings.document,
                page_number=non_current_borrowings.metric.source_page,
                quote=non_current_borrowings.metric.source_excerpt,
            ),
        ]
        calculations.append(
            _calculation(
                f"Total debt is calculated as current borrowings + non-current borrowings = {debt_value:f} {statement.period.currency} {statement.period.unit_scale}.",
                debt_citations,
                metric_key="total_debt",
                value=f"{debt_value:f}",
                currency=statement.period.currency,
                unit_scale=statement.period.unit_scale,
                period_label=statement.period.period_label,
            )
        )
    if debt_value is not None and equity and equity.value > 0:
        ratio = debt_value / equity.value
        calculations.append(
            _calculation(
                f"Debt/equity = total debt / total equity = {ratio:.2f}x for {statement.period.period_label}.",
                debt_citations
                + [_citation(equity.document, page_number=equity.metric.source_page, quote=equity.metric.source_excerpt)],
                metric_key="debt_equity_ratio",
                value=f"{ratio:.4f}",
                unit_scale="ratio",
            )
        )
    if debt_value is not None and cash:
        net_debt = debt_value - cash.value
        calculations.append(
            _calculation(
                f"Net debt = total debt - cash and equivalents = {net_debt:f} {statement.period.currency} {statement.period.unit_scale}.",
                debt_citations
                + [_citation(cash.document, page_number=cash.metric.source_page, quote=cash.metric.source_excerpt)],
                metric_key="net_debt",
                value=f"{net_debt:f}",
                currency=statement.period.currency,
                unit_scale=statement.period.unit_scale,
            )
        )
    assets = statement.metrics.get("total_assets")
    if debt_value is not None and assets and assets.value > 0:
        ratio = debt_value / assets.value
        calculations.append(
            _calculation(
                f"Debt/assets = total debt / total assets = {ratio:.2f}x for {statement.period.period_label}.",
                debt_citations
                + [_citation(assets.document, page_number=assets.metric.source_page, quote=assets.metric.source_excerpt)],
                metric_key="debt_assets_ratio",
                value=f"{ratio:.4f}",
                unit_scale="ratio",
            )
        )
    current_assets = statement.metrics.get("current_assets")
    current_liabilities = statement.metrics.get("current_liabilities")
    if current_assets and current_liabilities and current_liabilities.value > 0:
        ratio = current_assets.value / current_liabilities.value
        calculations.append(
            _calculation(
                f"Current ratio = current assets / current liabilities = {ratio:.2f}x for {statement.period.period_label}.",
                [
                    _citation(current_assets.document, page_number=current_assets.metric.source_page, quote=current_assets.metric.source_excerpt),
                    _citation(current_liabilities.document, page_number=current_liabilities.metric.source_page, quote=current_liabilities.metric.source_excerpt),
                ],
                metric_key="current_ratio",
                value=f"{ratio:.4f}",
                unit_scale="ratio",
            )
        )
    receivables = statement.metrics.get("trade_receivables")
    inventory = statement.metrics.get("inventory")
    payables = statement.metrics.get("trade_payables")
    revenue = statement.metrics.get("revenue")
    cogs = statement.metrics.get("cost_of_goods_sold")
    period_days = (statement.period.period_end - statement.period.period_start).days + 1
    day_components: dict[str, Decimal] = {}
    day_citations: list[dict[str, Any]] = []
    if receivables and revenue and revenue.value > 0:
        day_components["receivable_days"] = receivables.value / revenue.value * period_days
        day_citations.extend(
            [
                _citation(receivables.document, page_number=receivables.metric.source_page, quote=receivables.metric.source_excerpt),
                _citation(revenue.document, page_number=revenue.metric.source_page, quote=revenue.metric.source_excerpt),
            ]
        )
    if inventory and cogs and cogs.value > 0:
        day_components["inventory_days"] = inventory.value / cogs.value * period_days
        day_citations.extend(
            [
                _citation(inventory.document, page_number=inventory.metric.source_page, quote=inventory.metric.source_excerpt),
                _citation(cogs.document, page_number=cogs.metric.source_page, quote=cogs.metric.source_excerpt),
            ]
        )
    if payables and cogs and cogs.value > 0:
        day_components["payable_days"] = payables.value / cogs.value * period_days
        day_citations.extend(
            [
                _citation(payables.document, page_number=payables.metric.source_page, quote=payables.metric.source_excerpt),
                _citation(cogs.document, page_number=cogs.metric.source_page, quote=cogs.metric.source_excerpt),
            ]
        )
    for metric_key, label in (
        ("receivable_days", "Receivable days"),
        ("inventory_days", "Inventory days"),
        ("payable_days", "Payable days"),
    ):
        if metric_key in day_components:
            calculations.append(
                _calculation(
                    f"{label} = closing balance / annual flow × period days = {day_components[metric_key]:.1f} days; closing balances are used because average balances are unavailable.",
                    day_citations,
                    metric_key=metric_key,
                    value=f"{day_components[metric_key]:.2f}",
                    unit_scale="days",
                )
            )
    if all(key in day_components for key in ("receivable_days", "inventory_days", "payable_days")):
        cycle = (
            day_components["receivable_days"]
            + day_components["inventory_days"]
            - day_components["payable_days"]
        )
        calculations.append(
            _calculation(
                f"Working-capital cycle = receivable days + inventory days - payable days = {cycle:.1f} days; closing balances are used as a disclosed approximation.",
                day_citations,
                metric_key="working_capital_cycle_days",
                value=f"{cycle:.2f}",
                unit_scale="days",
            )
        )
    prior_annual = next(
        (
            item
            for item in statements
            if item.period.period_type == "year"
            and item.period.period_end < statement.period.period_end
            and (statement.period.period_end - item.period.period_end).days in range(330, 400)
        ),
        None,
    )
    pat = statement.metrics.get("pat")
    current_equity = statement.metrics.get("total_equity")
    prior_equity = prior_annual.metrics.get("total_equity") if prior_annual else None
    if pat and current_equity and prior_equity:
        if current_equity.metric.currency.upper() != prior_equity.metric.currency.upper():
            average_equity = Decimal(0)
        else:
            comparable_prior_equity = _scale(
                prior_equity.value,
                prior_annual.period.unit_scale,
                statement.period.unit_scale,
            )
            average_equity = (current_equity.value + comparable_prior_equity) / Decimal(2)
        if average_equity > 0:
            roe = pat.value / average_equity * Decimal(100)
            calculations.append(
                _calculation(
                    f"ROE = PAT / average opening and closing total equity = {roe:.2f}% for {statement.period.period_label}.",
                    [
                        _citation(pat.document, page_number=pat.metric.source_page, quote=pat.metric.source_excerpt),
                        _citation(current_equity.document, page_number=current_equity.metric.source_page, quote=current_equity.metric.source_excerpt),
                        _citation(prior_equity.document, page_number=prior_equity.metric.source_page, quote=prior_equity.metric.source_excerpt),
                    ],
                    metric_key="roe_pct",
                    value=f"{roe:.4f}",
                    unit_scale="percent",
                )
            )
    assets = statement.metrics.get("total_assets")
    current_liabilities = statement.metrics.get("current_liabilities")
    prior_assets = prior_annual.metrics.get("total_assets") if prior_annual else None
    prior_liabilities = (
        prior_annual.metrics.get("current_liabilities") if prior_annual else None
    )
    ebit = statement.metrics.get("ebit")
    same_currency = (
        assets
        and prior_assets
        and current_liabilities
        and prior_liabilities
        and assets.metric.currency.upper() == prior_assets.metric.currency.upper()
        and current_liabilities.metric.currency.upper()
        == prior_liabilities.metric.currency.upper()
    )
    if ebit and same_currency:
        opening_assets = _scale(
            prior_assets.value,
            prior_annual.period.unit_scale,
            statement.period.unit_scale,
        )
        opening_current_liabilities = _scale(
            prior_liabilities.value,
            prior_annual.period.unit_scale,
            statement.period.unit_scale,
        )
        average_capital_employed = (
            (assets.value - current_liabilities.value)
            + (opening_assets - opening_current_liabilities)
        ) / Decimal(2)
        if average_capital_employed > 0:
            roce = ebit.value / average_capital_employed * Decimal(100)
            calculations.append(
                _calculation(
                    f"ROCE = EBIT / average capital employed, where capital employed = total assets - current liabilities = {roce:.2f}% for {statement.period.period_label}.",
                    [
                        _citation(ebit.document, page_number=ebit.metric.source_page, quote=ebit.metric.source_excerpt),
                        _citation(assets.document, page_number=assets.metric.source_page, quote=assets.metric.source_excerpt),
                        _citation(current_liabilities.document, page_number=current_liabilities.metric.source_page, quote=current_liabilities.metric.source_excerpt),
                        _citation(prior_assets.document, page_number=prior_assets.metric.source_page, quote=prior_assets.metric.source_excerpt),
                        _citation(prior_liabilities.document, page_number=prior_liabilities.metric.source_page, quote=prior_liabilities.metric.source_excerpt),
                    ],
                    metric_key="roce_pct",
                    value=f"{roce:.4f}",
                    unit_scale="percent",
                )
            )
    return {
        "status": _section_status(facts, calculations, []),
        "facts": facts,
        "calculations": calculations,
        "interpretations": [],
        "observations": [
            {
                "period_label": statement.period.period_label,
                "period_end": statement.period.period_end.isoformat(),
                "convention": "Closing balance sheet values; no average-balance assumption.",
            }
        ],
        "limitations": [
            "Working-capital days use closing balances and are approximate; missing period-matched revenue or cost of goods sold suppresses affected ratios."
        ],
    }


def _cash_quality(statements: list[_Statement]) -> dict[str, Any]:
    candidates = [
        item
        for item in statements
        if item.period.period_type == "year"
        and any(key in item.metrics for key in ("cash_from_operations", "capital_expenditure", "pat"))
    ]
    facts: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for statement in candidates[:5]:
        for key in ("cash_from_operations", "capital_expenditure", "pat", "free_cash_flow"):
            fact = _metric_fact(statement, key)
            if fact:
                facts.append(fact)
        cfo = statement.metrics.get("cash_from_operations")
        capex = statement.metrics.get("capital_expenditure")
        pat = statement.metrics.get("pat")
        fcf = statement.metrics.get("free_cash_flow")
        if cfo and capex:
            calculated_fcf = cfo.value - abs(capex.value)
            calculations.append(
                _calculation(
                    f"Free cash flow = cash from operations - absolute capital expenditure = {calculated_fcf:f} {statement.period.currency} {statement.period.unit_scale} for {statement.period.period_label}.",
                    [
                        _citation(cfo.document, page_number=cfo.metric.source_page, quote=cfo.metric.source_excerpt),
                        _citation(capex.document, page_number=capex.metric.source_page, quote=capex.metric.source_excerpt),
                    ],
                    metric_key="free_cash_flow",
                    value=f"{calculated_fcf:f}",
                    currency=statement.period.currency,
                    unit_scale=statement.period.unit_scale,
                )
            )
        elif fcf:
            calculations.append(
                _calculation(
                    f"Free cash flow of {fcf.value:f} {fcf.metric.currency} {fcf.metric.unit_scale} was reported for {statement.period.period_label}; it was not recalculated.",
                    [_citation(fcf.document, page_number=fcf.metric.source_page, quote=fcf.metric.source_excerpt)],
                    metric_key="free_cash_flow",
                    value=f"{fcf.value:f}",
                    currency=fcf.metric.currency,
                    unit_scale=fcf.metric.unit_scale,
                )
            )
        if cfo and pat and pat.value > 0:
            conversion = cfo.value / pat.value
            calculations.append(
                _calculation(
                    f"Cash conversion (cash from operations / PAT) = {conversion:.2f}x for {statement.period.period_label}; closing cash-flow period values, no averaging.",
                    [
                        _citation(cfo.document, page_number=cfo.metric.source_page, quote=cfo.metric.source_excerpt),
                        _citation(pat.document, page_number=pat.metric.source_page, quote=pat.metric.source_excerpt),
                    ],
                    metric_key="cash_conversion_ratio",
                    value=f"{conversion:.4f}",
                    unit_scale="ratio",
                )
            )
        observations.append(
            {
                "period_label": statement.period.period_label,
                "cash_from_operations": str(cfo.value) if cfo else None,
                "capital_expenditure": str(capex.value) if capex else None,
                "free_cash_flow": (
                    str(cfo.value - abs(capex.value))
                    if cfo and capex
                    else str(fcf.value) if fcf else None
                ),
                "currency": statement.period.currency,
                "unit_scale": statement.period.unit_scale,
            }
        )
    return {
        "status": _section_status(facts, calculations, []),
        "facts": facts,
        "calculations": calculations,
        "interpretations": [],
        "observations": observations,
        "limitations": [] if candidates else [
            "Cash from operations and capital spending are not both available from an eligible annual source."
        ],
    }


def _guidance_metric(sentence: str) -> str | None:
    lowered = sentence.casefold()
    if "%" in sentence or "percent" in lowered:
        if ("ebitda" in lowered or "operating margin" in lowered) and "margin" in lowered:
            return "ebitda_margin_pct"
        if "ebitda" in lowered and re.search(r"grow|growth", lowered):
            return "ebitda_growth_pct"
        if "revenue" in lowered or "sales" in lowered:
            return "revenue_growth_pct" if re.search(r"growth|grow", lowered) else None
        return None
    matches = [
        (key, pattern)
        for key, pattern in (
            ("revenue", re.compile(r"\b(?:revenue|sales)\b", re.I)),
            ("ebitda", re.compile(r"\bebitda\b", re.I)),
            ("pat", re.compile(r"\b(?:pat|profit after tax|net profit)\b", re.I)),
            ("pbt", re.compile(r"\b(?:pbt|profit before tax)\b", re.I)),
            ("capital_expenditure", re.compile(r"\b(?:capex|capital expenditure)\b", re.I)),
        )
        if pattern.search(sentence)
    ]
    return matches[0][0] if len(matches) == 1 else None


def _parse_guidance_statement(
    sentence: str,
    document: Document,
    chunk: DocumentChunk,
) -> _GuidanceCandidate | None:
    if not _GUIDANCE_WORDS.search(sentence):
        return None
    metric_key = _guidance_metric(sentence)
    if metric_key is None:
        return None
    if metric_key.endswith("_pct"):
        ranges = list(_PERCENT_RANGE.finditer(sentence))
        if ranges:
            numbers = [
                number
                for match in ranges
                for number in (
                    Decimal(match.group("low")),
                    Decimal(match.group("high")),
                )
            ]
        else:
            numbers = [Decimal(match.group("number")) for match in _PERCENT.finditer(sentence)]
        if not 1 <= len(numbers) <= 2:
            return None
        unit = "percent"
        currency = None
    else:
        amounts = list(_MONEY_TARGET.finditer(sentence))
        if len(amounts) != 1:
            return None
        amount = amounts[0]
        unit_token = amount.group("unit").casefold()
        unit = (
            "crore" if unit_token in {"crore", "crores", "cr"}
            else "lakh" if unit_token in {"lakh", "lakhs", "lac", "lacs"}
            else "million" if unit_token in {"million", "millions", "mn"}
            else "billion" if unit_token in {"billion", "billions", "bn"}
            else "thousand"
        )
        currency = "INR" if "₹" in sentence or re.search(r"\b(?:INR|Rs\.?)\b", sentence, re.I) else None
        if currency is None:
            return None
        numbers = [
            Decimal(amount.group("low").replace(",", "")),
            *(
                [Decimal(amount.group("high").replace(",", ""))]
                if amount.group("high")
                else []
            ),
        ]
    period_label, target_start, target_end = _period_from_text(sentence)
    if len(numbers) == 1:
        low = high = numbers[0]
    else:
        low, high = min(numbers), max(numbers)
    return _GuidanceCandidate(
        document=document,
        chunk=chunk,
        statement=sentence.strip(),
        metric_key=metric_key,
        target_low=low,
        target_high=high,
        currency=currency,
        unit_scale=unit,
        target_start=target_start,
        target_end=target_end,
        target_label=period_label,
    )


def _guidance_candidates(
    session: Session,
    company_id: UUID,
    quarters: int,
) -> tuple[list[tuple[Document, list[tuple[DocumentChunk, str]]]], list[_GuidanceCandidate]]:
    documents = session.scalars(
        select(Document)
        .where(
            Document.company_id == company_id,
            Document.document_type == "earnings_call_transcript",
            Document.is_primary_source.is_(True),
            Document.synthetic.is_(False),
            Document.ingestion_status.in_(("extracted", "embedded")),
            Document.period_end.is_not(None),
        )
        .order_by(Document.period_end.desc())
    ).all()
    unique_by_period: dict[date, Document] = {}
    for document in documents:
        if document.period_end not in unique_by_period:
            unique_by_period[document.period_end] = document
    selected_documents = sorted(
        unique_by_period.values(),
        key=lambda item: item.period_end or date.min,
        reverse=True,
    )[:quarters]
    commentary_by_document: list[tuple[Document, list[tuple[DocumentChunk, str]]]] = []
    candidates: list[_GuidanceCandidate] = []
    for document in selected_documents:
        chunks = session.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.synthetic.is_(False),
            )
            .order_by(DocumentChunk.chunk_index)
        ).all()
        commentary: list[tuple[DocumentChunk, str]] = []
        seen_statements: set[str] = set()
        for chunk in chunks:
            for raw_statement in re.split(r"(?<=[.!?])\s+|\n+", chunk.text):
                statement = " ".join(raw_statement.split()).strip(" |")
                if len(statement) < 25 or not _COMMENTARY_WORDS.search(statement):
                    continue
                normalized = statement.casefold()
                if normalized in seen_statements:
                    continue
                seen_statements.add(normalized)
                candidate = _parse_guidance_statement(statement, document, chunk)
                if candidate is not None:
                    candidates.append(candidate)
                if len(commentary) < 5:
                    commentary.append((chunk, statement[:1500]))
        commentary_by_document.append((document, commentary))
    return commentary_by_document, candidates


def _persist_guidance(
    session: Session,
    company_id: UUID,
    candidates: list[_GuidanceCandidate],
) -> list[ManagementGuidance]:
    persisted: list[ManagementGuidance] = []
    for item in candidates:
        digest = hashlib.sha256(
            f"{item.document.id}|{item.metric_key}|{item.statement}".encode("utf-8")
        ).hexdigest()[:24]
        key = f"source-{digest}"
        row = session.scalar(
            select(ManagementGuidance).where(
                ManagementGuidance.company_id == company_id,
                ManagementGuidance.guidance_key == key,
            )
        )
        if row is None:
            row = ManagementGuidance(
                company_id=company_id,
                document_id=item.document.id,
                guidance_key=key,
                metric_key=item.metric_key,
                statement=item.statement,
                period_start=item.target_start,
                period_end=item.target_end,
                target_low=item.target_low,
                target_high=item.target_high,
                currency=item.currency,
                unit_scale=item.unit_scale,
                source_page=item.chunk.page_start,
                source_excerpt=item.statement,
                confidence=None,
                is_synthetic=False,
            )
            session.add(row)
            session.flush()
        persisted.append(row)
    return persisted


def _actual_for_guidance(
    candidate: _GuidanceCandidate,
    statements: list[_Statement],
    reporting_basis: str,
) -> tuple[Decimal | None, _Statement | None, str | None]:
    if candidate.target_start is None or candidate.target_end is None:
        return None, None, "The statement did not specify a target reporting period."
    target_statement = next(
        (
            item
            for item in statements
            if item.period.period_start == candidate.target_start
            and item.period.period_end == candidate.target_end
            and item.period.reporting_basis == reporting_basis
        ),
        None,
    )
    if target_statement is None:
        return None, None, "No actual financial period matching the explicit guidance period is available."
    metric_key = candidate.metric_key
    if metric_key.endswith("_growth_pct"):
        source_metric_key = metric_key.removesuffix("_growth_pct")
        current = target_statement.metrics.get(source_metric_key)
        prior_end = _shift_months(target_statement.period.period_end, -12)
        previous = next(
            (
                item
                for item in statements
                if item.period.period_end == prior_end
                and item.period.period_type == target_statement.period.period_type
                and item.period.reporting_basis == target_statement.period.reporting_basis
                and item.period.currency.upper() == target_statement.period.currency.upper()
            ),
            None,
        )
        prior_metric = previous.metrics.get(source_metric_key) if previous else None
        if not current or not prior_metric:
            return None, target_statement, f"Comparable current and prior-year {source_metric_key} are unavailable."
        comparable_prior = _scale(
            prior_metric.value,
            previous.period.unit_scale,
            target_statement.period.unit_scale,
        )
        change = _percent_change(current.value, comparable_prior)
        if change is None:
            return None, target_statement, "A non-positive prior-year base prevents a meaningful growth percentage."
        return change, target_statement, None
    if metric_key == "ebitda_margin_pct":
        ebitda = target_statement.metrics.get("ebitda")
        revenue = target_statement.metrics.get("revenue")
        if not ebitda or not revenue or revenue.value == 0:
            return None, target_statement, "Actual EBITDA margin inputs are unavailable."
        return ebitda.value / revenue.value * Decimal(100), target_statement, None
    metric = target_statement.metrics.get(metric_key)
    if metric is None:
        return None, target_statement, f"Actual {metric_key.replace('_', ' ')} is unavailable for the target period."
    if candidate.currency and metric.metric.currency.upper() != candidate.currency.upper():
        return None, target_statement, "Guidance and actual use different currencies."
    try:
        actual = _scale(
            metric.value,
            target_statement.period.unit_scale,
            candidate.unit_scale,
        )
    except ValueError:
        return None, target_statement, "Guidance and actual use incompatible units."
    return actual, target_statement, None


def _outcome(
    actual: Decimal | None,
    candidate: _GuidanceCandidate | None,
    unavailable_reason: str | None,
) -> str:
    if actual is None or candidate is None or unavailable_reason:
        return "not_yet_verifiable"
    if candidate.target_low == candidate.target_high:
        if actual == candidate.target_low:
            return "met"
        return "exceeded" if actual > candidate.target_high else "missed"
    if actual < candidate.target_low:
        return "missed"
    if actual > candidate.target_high:
        return "exceeded"
    return "met"


def _render_guidance_rows(
    commentary: list[tuple[Document, list[tuple[DocumentChunk, str]]]],
    candidates: list[_GuidanceCandidate],
    statements: list[_Statement],
    persisted: list[ManagementGuidance],
    session: Session,
    reporting_basis: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates_by_document: dict[UUID, list[_GuidanceCandidate]] = {}
    for candidate in candidates:
        candidates_by_document.setdefault(candidate.document.id, []).append(candidate)
    persisted_by_key = {row.guidance_key: row for row in persisted}
    for document, statements_for_doc in commentary:
        document_candidates = candidates_by_document.get(document.id, [])
        if not document_candidates:
            for chunk, statement in statements_for_doc[:2]:
                actual_statement = next(
                    (
                        item
                        for item in statements
                        if item.period.period_end == document.period_end
                        and item.period.period_type == "quarter"
                        and item.period.reporting_basis == reporting_basis
                    ),
                    None,
                )
                actual_metrics = (
                    [
                        _metric_fact(actual_statement, key)
                        for key in ("revenue", "ebitda", "pbt", "pat")
                        if _metric_fact(actual_statement, key) is not None
                    ]
                    if actual_statement
                    else []
                )
                rows.append(
                    {
                        "statement_date": (
                            document.published_at.date().isoformat()
                            if document.published_at
                            else document.fetched_at.date().isoformat()
                        ),
                        "quarter": document.period_label or "Quarter unavailable",
                        "management_statement": statement,
                        "metric_key": None,
                        "expected_result": None,
                        "actual_result": (
                            "; ".join(item["text"] for item in actual_metrics)
                            if actual_metrics
                            else None
                        ),
                        "variance": None,
                        "assessment": "not_yet_verifiable",
                        "citations": [
                            _citation(
                                document,
                                page_number=chunk.page_start,
                                quote=statement,
                                chunk_id=chunk.id,
                            ),
                            *[
                                citation
                                for fact in actual_metrics
                                for citation in fact["citations"]
                            ],
                        ],
                    }
                )
            continue
        for candidate in document_candidates:
            actual, actual_statement, reason = _actual_for_guidance(
                candidate,
                statements,
                reporting_basis,
            )
            assessment = _outcome(actual, candidate, reason)
            expected = (
                f"{candidate.target_low:g}"
                if candidate.target_low == candidate.target_high
                else f"{candidate.target_low:g}–{candidate.target_high:g}"
            )
            if candidate.unit_scale == "percent":
                expected += "%"
            else:
                expected += f" {candidate.currency} {candidate.unit_scale}"
            actual_display = f"{actual:g} {candidate.unit_scale}" if actual is not None else None
            variance = None
            if actual is not None:
                delta = actual - candidate.target_high if actual > candidate.target_high else actual - candidate.target_low if actual < candidate.target_low else Decimal(0)
                variance = f"{delta:+g} {candidate.unit_scale} vs guidance range"
            citations = [
                _citation(
                    candidate.document,
                    page_number=candidate.chunk.page_start,
                    quote=candidate.statement,
                    chunk_id=candidate.chunk.id,
                )
            ]
            metric_id = None
            if actual_statement:
                actual_metric_key = candidate.metric_key.removesuffix("_growth_pct")
                actual_metric_keys = (
                    ("ebitda", "revenue")
                    if candidate.metric_key == "ebitda_margin_pct"
                    else (actual_metric_key,)
                )
                actual_metric = None
                for source_metric_key in actual_metric_keys:
                    source_metric = actual_statement.metrics.get(source_metric_key)
                    if source_metric is None:
                        continue
                    if actual_metric is None:
                        actual_metric = source_metric
                        metric_id = source_metric.metric.id
                    citations.append(
                        _citation(
                            source_metric.document,
                            page_number=source_metric.metric.source_page,
                            quote=source_metric.metric.source_excerpt,
                        )
                    )
                if actual_metric and candidate.metric_key.endswith("_growth_pct"):
                        prior_end = _shift_months(actual_statement.period.period_end, -12)
                        prior_statement = next(
                            (
                                item
                                for item in statements
                                if item.period.period_end == prior_end
                                and item.period.period_type == actual_statement.period.period_type
                                and item.period.reporting_basis == actual_statement.period.reporting_basis
                            ),
                            None,
                        )
                        prior_metric = (
                            prior_statement.metrics.get(actual_metric_key)
                            if prior_statement
                            else None
                        )
                        if prior_metric:
                            citations.append(
                                _citation(
                                    prior_metric.document,
                                    page_number=prior_metric.metric.source_page,
                                    quote=prior_metric.metric.source_excerpt,
                                )
                            )
            guidance_key = "source-" + hashlib.sha256(
                f"{candidate.document.id}|{candidate.metric_key}|{candidate.statement}".encode("utf-8")
            ).hexdigest()[:24]
            guidance_row = persisted_by_key.get(guidance_key)
            if guidance_row:
                assessment_document = actual_statement.document if actual_statement else candidate.document
                assessed = session.scalar(
                    select(GuidanceAssessment).where(
                        GuidanceAssessment.guidance_id == guidance_row.id,
                        GuidanceAssessment.assessment_document_id == assessment_document.id,
                    )
                )
                if assessed is None:
                    assessed = GuidanceAssessment(
                        guidance_id=guidance_row.id,
                        assessment_document_id=assessment_document.id,
                        financial_metric_id=metric_id,
                        outcome=assessment,
                        actual_value=actual,
                        rationale=reason or f"Compared actual {candidate.metric_key} with the explicit source-stated target.",
                        source_excerpt=candidate.statement,
                        is_synthetic=False,
                    )
                    session.add(assessed)
                else:
                    assessed.financial_metric_id = metric_id
                    assessed.outcome = assessment
                    assessed.actual_value = actual
                    assessed.rationale = reason or "Recomputed from matching primary-source financial data."
            rows.append(
                {
                    "statement_date": (
                        candidate.document.published_at.date().isoformat()
                        if candidate.document.published_at
                        else candidate.document.fetched_at.date().isoformat()
                    ),
                    "quarter": candidate.document.period_label or "Quarter unavailable",
                    "target_period": candidate.target_label,
                    "management_statement": candidate.statement,
                    "metric_key": candidate.metric_key,
                    "expected_result": expected,
                    "actual_result": actual_display,
                    "variance": variance or reason,
                    "assessment": assessment,
                    "citations": citations,
                }
            )
    return rows


def _narrative_guidance(
    session: Session,
    company_id: UUID,
    statements: list[_Statement],
    quarters: int,
    reporting_basis: str,
    *,
    persist_guidance: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    commentary, candidates = _guidance_candidates(session, company_id, quarters)
    persisted = (
        _persist_guidance(session, company_id, candidates)
        if persist_guidance
        else []
    )
    rows = _render_guidance_rows(
        commentary,
        candidates,
        statements,
        persisted,
        session,
        reporting_basis,
    )
    session.flush()
    sources = [
        _citation(
            document,
            page_number=chunk.page_start,
            quote=statement,
            chunk_id=chunk.id,
        )
        for document, statements_for_doc in commentary
        for chunk, statement in statements_for_doc
    ]
    narrative = {
        "status": "ready" if rows else "unavailable",
        "facts": [
            {
                "text": row["management_statement"],
                "claim_type": "reported_fact",
                "citations": row["citations"][:1],
            }
            for row in rows
        ],
        "calculations": [],
        "interpretations": [],
        "observations": rows,
        "limitations": [] if rows else [
            "No indexed primary-source earnings-call commentary was found for the requested quarters."
        ],
    }
    guidance = {
        "status": "ready" if any(item.metric_key for item in candidates) else "partial" if rows else "unavailable",
        "facts": narrative["facts"],
        "calculations": [],
        "interpretations": [],
        "observations": rows,
        "limitations": (
            []
            if any(item.metric_key for item in candidates)
            else ["No explicit, uniquely parseable numerical management guidance was identified; qualitative commentary is not converted into a target."]
        ),
        "source_references": sources,
    }
    return narrative, guidance


def _bull_bear(statements: list[_Statement]) -> dict[str, Any]:
    annual = sorted(
        (item for item in statements if item.period.period_type == "year"),
        key=lambda item: item.period.period_end,
    )
    facts: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []
    interpretations: list[dict[str, Any]] = []
    if len(annual) >= 2:
        current, previous = annual[-1], annual[-2]
        for key in ("revenue", "pat"):
            now, before = current.metrics.get(key), previous.metrics.get(key)
            if not now or not before:
                continue
            if now.metric.currency.upper() != before.metric.currency.upper():
                continue
            comparable_before = _scale(
                before.value,
                previous.period.unit_scale,
                current.period.unit_scale,
            )
            change = _percent_change(now.value, comparable_before)
            if change is None:
                continue
            claim = _calculation(
                f"{key.replace('_', ' ').title()} changed {change:.2f}% from {previous.period.period_label} to {current.period.period_label}.",
                [
                    _citation(now.document, page_number=now.metric.source_page, quote=now.metric.source_excerpt),
                    _citation(before.document, page_number=before.metric.source_page, quote=before.metric.source_excerpt),
                ],
                metric_key=f"{key}_yoy_pct",
                value=f"{change:.4f}",
            )
            calculations.append(claim)
            if change > 0:
                interpretations.append(
                    {
                        "text": f"Bull case: reported {key.replace('_', ' ')} increased year on year, a positive historical indicator rather than a forecast.",
                        "claim_type": "interpretation",
                        "citations": claim["citations"],
                    }
                )
            elif change < 0:
                interpretations.append(
                    {
                        "text": f"Bear case: reported {key.replace('_', ' ')} declined year on year, indicating recent pressure rather than a prediction of future results.",
                        "claim_type": "interpretation",
                        "citations": claim["citations"],
                    }
                )
        latest = annual[-1]
        cfo, pat = latest.metrics.get("cash_from_operations"), latest.metrics.get("pat")
        if cfo and pat:
            citations = [
                _citation(cfo.document, page_number=cfo.metric.source_page, quote=cfo.metric.source_excerpt),
                _citation(pat.document, page_number=pat.metric.source_page, quote=pat.metric.source_excerpt),
            ]
            if pat.value > 0 and cfo.value < pat.value:
                interpretations.append(
                    {
                        "text": "Bear case: cash from operations was below reported PAT in the latest annual period; investigate conversion quality and timing.",
                        "claim_type": "interpretation",
                        "citations": citations,
                    }
                )
            elif pat.value > 0 and cfo.value >= pat.value:
                interpretations.append(
                    {
                        "text": "Bull case: cash from operations equalled or exceeded reported PAT in the latest annual period; this supports, but does not guarantee, earnings cash conversion.",
                        "claim_type": "interpretation",
                        "citations": citations,
                    }
                )
    return {
        "status": _section_status(facts, calculations, interpretations),
        "facts": facts,
        "calculations": calculations,
        "interpretations": interpretations,
        "observations": [
            {
                "disclaimer": "Evidence-backed analytical considerations only; not a buy/sell recommendation or forecast."
            }
        ],
        "limitations": [] if interpretations else [
            "Insufficient comparable annual financial evidence to form a balanced bull/bear case."
        ],
    }


def _metric_periods(
    session: Session,
    company_id: UUID,
    reporting_basis: str,
) -> list[dict[str, Any]]:
    statements = _load_statements(session, company_id, reporting_basis)
    result: list[dict[str, Any]] = []
    for statement in statements:
        metrics = {
            key: {
                "value": str(item.metric.reported_value),
                "currency": item.metric.currency,
                "unit_scale": item.metric.unit_scale,
                "source_page": item.metric.source_page,
                "source_url": item.document.source_url,
                "source_excerpt": item.metric.source_excerpt,
                "metric_id": str(item.metric.id),
            }
            for key, item in statement.metrics.items()
        }
        result.append(
            {
                "period_id": str(statement.period.id),
                "period_label": statement.period.period_label,
                "period_start": statement.period.period_start.isoformat(),
                "period_end": statement.period.period_end.isoformat(),
                "period_type": statement.period.period_type,
                "reporting_basis": statement.period.reporting_basis,
                "currency": statement.period.currency,
                "unit_scale": statement.period.unit_scale,
                "document_id": str(statement.document.id),
                "document_name": statement.document.title,
                "source_url": statement.document.source_url,
                "metrics": metrics,
            }
        )
    return result


def build_financial_research_report(
    session: Session,
    *,
    company_id: UUID,
    ticker: str,
    reporting_basis: str = "consolidated",
    quarters: int = 4,
    persist_guidance: bool = True,
) -> dict[str, Any]:
    if reporting_basis not in {"standalone", "consolidated"}:
        raise ValueError("reporting_basis must be standalone or consolidated.")
    if not 1 <= quarters <= 4:
        raise ValueError("quarters must be between 1 and 4.")
    company = session.get(Company, company_id)
    if company is None:
        raise LookupError(f"Company {company_id} is unavailable.")

    statements = _load_statements(session, company_id, reporting_basis)
    chunks = _source_chunks(
        session,
        company_id,
        ("annual_report", "quarterly_result", "earnings_call_transcript", "investor_presentation"),
    )
    narrative, guidance = _narrative_guidance(
        session,
        company_id,
        statements,
        quarters,
        reporting_basis,
        persist_guidance=persist_guidance,
    )
    sections = {
        "business_snapshot": _business_snapshot(chunks),
        "financial_snapshot": _financial_snapshot(statements),
        "financial_trajectory": _trajectory(statements),
        "balance_sheet_analysis": _balance_sheet(statements),
        "cash_quality_analysis": _cash_quality(statements),
        "narrative_vs_numbers": narrative,
        "management_guidance": guidance,
        "bull_vs_bear": _bull_bear(statements),
    }
    references: dict[tuple[str, int | None, str | None], dict[str, Any]] = {}
    for section in sections.values():
        for key in ("facts", "calculations", "interpretations"):
            for claim in section.get(key, []):
                for citation in claim["citations"]:
                    references[
                        (
                            str(citation["document_id"]),
                            citation.get("page_number"),
                            citation.get("quote"),
                        )
                    ] = citation
    for row in guidance.get("observations", []):
        for citation in row.get("citations", []):
            references[
                (
                    str(citation["document_id"]),
                    citation.get("page_number"),
                    citation.get("quote"),
                )
            ] = citation
    section_statuses = [item["status"] for item in sections.values()]
    status = (
        "complete"
        if section_statuses and all(value == "ready" for value in section_statuses)
        else "partial"
        if any(value != "unavailable" for value in section_statuses)
        else "unavailable"
    )
    return {
        "ticker": ticker,
        "company_name": company.display_name,
        "generated_at": datetime.now(timezone.utc),
        "status": status,
        "source_count": len({key[0] for key in references}),
        "source_manifest": list(references.values()),
        "model_route": "deterministic_primary_source_v1",
        "is_synthetic": False,
        **sections,
    }


def search_companies(
    session: Session,
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    term = query.strip()
    if len(term) < 2:
        raise ValueError("Company search query must contain at least two characters.")
    if not 1 <= limit <= 50:
        raise ValueError("Company search limit must be between 1 and 50.")
    pattern = f"%{term}%"
    aliases = session.execute(
        select(CompanyAlias, Company)
        .join(Company, Company.id == CompanyAlias.company_id)
        .where(
            CompanyAlias.exchange == "NSE",
            (CompanyAlias.normalized_symbol.ilike(pattern))
            | (Company.display_name.ilike(pattern))
            | (Company.legal_name.ilike(pattern)),
        )
        .order_by(Company.display_name, CompanyAlias.normalized_symbol)
        .limit(limit)
    ).all()
    results: list[dict[str, Any]] = []
    for alias, company in aliases:
        has_documents = session.scalar(
            select(Document.id)
            .where(
                Document.company_id == company.id,
                Document.is_primary_source.is_(True),
                Document.synthetic.is_(False),
            )
            .limit(1)
        ) is not None
        has_metrics = session.scalar(
            select(FinancialStatementPeriod.id)
            .where(
                FinancialStatementPeriod.company_id == company.id,
                FinancialStatementPeriod.is_synthetic.is_(False),
            )
            .limit(1)
        ) is not None
        results.append(
            {
                "ticker": alias.normalized_symbol,
                "exchange": alias.exchange,
                "company_id": company.id,
                "company_name": company.display_name,
                "sector": company.sector,
                "has_primary_documents": has_documents,
                "has_financial_data": has_metrics,
            }
        )
    return results


def list_primary_sources(session: Session, company_id: UUID) -> list[dict[str, Any]]:
    documents = session.scalars(
        select(Document)
        .where(
            Document.company_id == company_id,
            Document.is_primary_source.is_(True),
            Document.synthetic.is_(False),
            Document.document_type.in_(
                ("annual_report", "quarterly_result", "earnings_call_transcript", "investor_presentation")
            ),
        )
        .order_by(Document.period_end.desc(), Document.published_at.desc())
    ).all()
    result: list[dict[str, Any]] = []
    for document in documents:
        result.append(_citation(document, page_number=None, quote=None))
    return result


def list_financial_periods(
    session: Session,
    company_id: UUID,
    reporting_basis: str,
) -> list[dict[str, Any]]:
    if reporting_basis not in {"standalone", "consolidated"}:
        raise ValueError("reporting_basis must be standalone or consolidated.")
    return _metric_periods(session, company_id, reporting_basis)


def company_for_ticker(session: Session, ticker: str) -> tuple[Company, CompanyAlias]:
    normalized = ticker.strip().upper().removesuffix(".NS")
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == normalized,
        )
    )
    if alias is None:
        raise LookupError(f"No NSE company mapping exists for ticker {normalized}.")
    company = session.get(Company, alias.company_id)
    if company is None:
        raise LookupError(f"The NSE mapping for {normalized} has no canonical company.")
    return company, alias


__all__ = [
    "build_financial_research_report",
    "company_for_ticker",
    "list_financial_periods",
    "list_primary_sources",
    "search_companies",
]
