from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.db.models import (
    Document,
    DocumentChunk,
    FinancialMetric,
    FinancialStatementPeriod,
)

FINANCIAL_METRIC_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cash_from_operations", re.compile(r"^(?:net cash (?:generated from|from) operating activities|net cash flow from operating activities|cash flow from operating activities|cash from operations)\b", re.I)),
    ("capital_expenditure", re.compile(r"^(?:capital expenditure|capital expenditures|capex|expenditure for property,\s*plant and equipment|purchase of property,\s*plant and equipment|purchase of fixed assets)\b", re.I)),
    ("cash_and_equivalents", re.compile(r"^(?:cash and cash equivalents|cash equivalents|cash and bank balances|cash balance)\b", re.I)),
    ("trade_receivables", re.compile(r"^(?:trade receivables|accounts receivable|receivables)\b", re.I)),
    ("trade_payables", re.compile(r"^(?:trade payables|accounts payable|payables)\b", re.I)),
    ("total_debt", re.compile(r"^(?:total borrowings|borrowings|total debt|debt)\b", re.I)),
    ("total_equity", re.compile(r"^(?:total equity(?!\s+and liabilities)|shareholders['’] funds|equity attributable to owners)\b", re.I)),
    ("current_assets", re.compile(r"^(?:total )?current assets\b", re.I)),
    ("current_liabilities", re.compile(r"^(?:total )?current liabilities\b", re.I)),
    ("total_assets", re.compile(r"^total assets\b", re.I)),
    ("inventory", re.compile(r"^(?:inventories|inventory|stock-in-trade)\b", re.I)),
    ("ebitda", re.compile(r"^ebitda\b", re.I)),
    ("revenue", re.compile(r"^(?:revenue from operations|total revenue|revenue|sales)\b", re.I)),
    ("pbt", re.compile(r"^(?:profit before.*\band tax|profit before taxation|pbt)\b", re.I)),
    ("pat", re.compile(r"^(?:profit after tax|profit for the period|profit for the year|pat|net profit(?! before))\b", re.I)),
    ("cost_of_goods_sold", re.compile(r"^(?:cost of goods sold|cost of sales)\b", re.I)),
    ("ebit", re.compile(r"^ebit\b", re.I)),
    ("interest_expense", re.compile(r"^(?:finance costs|interest expense|finance charges)\b", re.I)),
    ("free_cash_flow", re.compile(r"^(?:free cash flow|fcf)\b", re.I)),
)

_NUMBER = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![\w.%])")
_UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("crore", re.compile(r"\b(?:in\s+)?crores?\b|\bcr\b", re.I)),
    ("lakh", re.compile(r"\b(?:in\s+)?lakhs?\b|\blacs?\b", re.I)),
    ("million", re.compile(r"\bmillions?\b|\bmn\b", re.I)),
    ("billion", re.compile(r"\bbillions?\b|\bbn\b", re.I)),
    ("thousand", re.compile(r"\bthousands?\b", re.I)),
    ("unit", re.compile(r"\b(?:in\s+)?rupees?\b|\bunits?\b", re.I)),
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
_FINANCIAL_LAYOUT_MARKER = "FINANCIAL_STATEMENT_LAYOUT:"


@dataclass(frozen=True)
class ExtractedFinancialValue:
    metric_key: str
    value: Decimal
    currency: str
    unit_scale: str
    page_number: int
    source_excerpt: str


@dataclass(frozen=True)
class FinancialExtractionOutcome:
    period_id: UUID
    extracted: tuple[ExtractedFinancialValue, ...]
    ambiguous_metric_keys: tuple[str, ...]


def _unit_in_text(text: str, fallback: str) -> str:
    for unit, pattern in _UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return fallback


def _currency_in_text(text: str, fallback: str) -> str:
    if "₹" in text or re.search(r"\b(?:INR|Rs\.?)\b", text, re.I):
        return "INR"
    if re.search(r"\bUSD\b|\$", text, re.I):
        return "USD"
    return fallback.upper()


def _parse_value(raw: str) -> Decimal:
    negative_parentheses = raw.startswith("(") and raw.endswith(")")
    value = Decimal(raw.replace(",", "").strip("()"))
    return -value if negative_parentheses else value


def extract_financial_values(
    pages: Iterable[tuple[int, str]],
    *,
    currency: str,
    default_unit_scale: str,
    period_label: str | None = None,
    reporting_basis: str | None = None,
) -> tuple[tuple[ExtractedFinancialValue, ...], tuple[str, ...]]:
    """Extract only uniquely labelled, single-value rows; ambiguous rows are withheld."""
    fallback_unit = default_unit_scale.casefold().strip()
    if fallback_unit not in _UNIT_FACTORS:
        raise ValueError(f"Unsupported financial unit scale: {default_unit_scale}")
    if not re.fullmatch(r"[A-Za-z]{3}", currency):
        raise ValueError("currency must be a three-letter ISO currency code.")

    page_list = list(pages)
    if period_label and reporting_basis:
        layout_values = _extract_annual_layout_values(
            page_list,
            period_label=period_label,
            reporting_basis=reporting_basis,
            currency=currency,
            default_unit_scale=fallback_unit,
        )
        if layout_values is not None:
            return layout_values

    candidates: dict[str, list[ExtractedFinancialValue]] = {}
    ambiguous_lines: set[str] = set()
    for page_number, text in page_list:
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("#").strip()
            for metric_key, label_pattern in FINANCIAL_METRIC_LABELS:
                label_match = label_pattern.match(line)
                if label_match is None:
                    continue
                remainder = line[label_match.end() :]
                matches = list(_NUMBER.finditer(remainder))
                if len(matches) != 1:
                    if matches:
                        ambiguous_lines.add(metric_key)
                    break
                number = matches[0]
                unit = _unit_in_text(line, fallback_unit)
                candidates.setdefault(metric_key, []).append(
                    ExtractedFinancialValue(
                        metric_key=metric_key,
                        value=_parse_value(number.group()),
                        currency=_currency_in_text(line, currency),
                        unit_scale=unit,
                        page_number=page_number,
                        source_excerpt=line,
                    )
                )
                break

    extracted: list[ExtractedFinancialValue] = []
    ambiguous = set(ambiguous_lines)
    for metric_key, values in candidates.items():
        if len(values) == 1 and metric_key not in ambiguous:
            extracted.append(values[0])
        else:
            ambiguous.add(metric_key)
    return tuple(sorted(extracted, key=lambda value: value.metric_key)), tuple(sorted(ambiguous))


def _extract_annual_layout_values(
    pages: list[tuple[int, str]],
    *,
    period_label: str,
    reporting_basis: str,
    currency: str,
    default_unit_scale: str,
) -> tuple[tuple[ExtractedFinancialValue, ...], tuple[str, ...]] | None:
    period_match = re.search(r"(20\d{2})\s*[-–/]\s*(\d{2,4})", period_label)
    if period_match is None:
        return None
    start_year = int(period_match.group(1))
    end_part = period_match.group(2)
    end_year = (
        int(f"{str(start_year)[:2]}{end_part}")
        if len(end_part) == 2
        else int(end_part)
    )
    target_range = f"{start_year}-{str(end_year)[-2:]}"
    basis_pattern = re.compile(
        rf"\b{re.escape(reporting_basis)}\s+financial statements\b",
        re.I,
    )
    layout_pages: list[tuple[int, str, str]] = []
    for page_number, text in pages:
        if _FINANCIAL_LAYOUT_MARKER not in text or not basis_pattern.search(text):
            continue
        _, layout = text.split(_FINANCIAL_LAYOUT_MARKER, 1)
        normalized_layout = re.sub(r"\s+", " ", layout).casefold()
        if str(end_year) not in normalized_layout:
            continue
        title_block = normalized_layout[:400]
        if re.search(
            r"\bconsolidated\s+(?:balance sheet|statement of profit and loss|statement of cash flows?)\b",
            title_block,
        ) or re.search(
            r"\bstandalone\s+(?:balance sheet|statement of profit and loss|statement of cash flows?)\b",
            title_block,
        ):
            layout_pages.append((page_number, text, layout))
    if not layout_pages:
        return None

    section_keys = {
        "balance": {
            "current_borrowings",
            "non_current_borrowings",
            "cash_and_equivalents",
            "total_equity",
            "current_assets",
            "current_liabilities",
            "total_assets",
            "trade_receivables",
            "trade_payables",
            "inventory",
        },
        "profit": {"revenue", "ebitda", "pbt", "pat", "interest_expense", "ebit"},
        "cash": {"cash_from_operations", "capital_expenditure"},
    }
    candidates: dict[str, list[ExtractedFinancialValue]] = {}
    ambiguous: set[str] = set()
    for page_number, _, layout in layout_pages:
        lowered = re.sub(r"\s+", " ", layout).casefold()[:400]
        if re.search(r"\bstatement of cash flows?\b", lowered):
            section_name = "cash"
            allowed = section_keys["cash"]
        elif re.search(r"\bstatement of profit and loss\b", lowered):
            section_name = "profit"
            allowed = section_keys["profit"]
        elif re.search(r"\bbalance sheet\b", lowered):
            section_name = "balance"
            allowed = section_keys["balance"]
        else:
            continue
        current_liabilities_section = False
        for raw_line in layout.splitlines():
            normalized_line = re.sub(r"\s+", " ", raw_line).strip().casefold()
            if re.search(r"\bnon[- ]current liabilities\b", normalized_line):
                current_liabilities_section = False
            elif re.search(r"\bcurrent liabilities\b", normalized_line):
                current_liabilities_section = True
            row_segments = re.split(r"\s{3,}(?=[A-Za-z])", raw_line.strip())
            for line in row_segments:
                for metric_key, label_pattern in FINANCIAL_METRIC_LABELS:
                    output_key = metric_key
                    if metric_key == "total_debt" and section_name == "balance":
                        output_key = (
                            "current_borrowings"
                            if current_liabilities_section
                            else "non_current_borrowings"
                        )
                    if metric_key == "total_debt" and section_name != "balance":
                        continue
                    if output_key not in allowed:
                        continue
                    label = re.compile(label_pattern.pattern.removeprefix("^"), label_pattern.flags)
                    label_match = label.match(line)
                    if label_match is None:
                        continue
                    matches = list(_NUMBER.finditer(line[label_match.end() :]))
                    if len(matches) < 2:
                        if matches:
                            ambiguous.add(output_key)
                        break
                    current_value = _parse_value(matches[-2].group())
                    candidates.setdefault(output_key, []).append(
                        ExtractedFinancialValue(
                            metric_key=output_key,
                            value=current_value,
                            currency=_currency_in_text(line, currency),
                            unit_scale=_unit_in_text(line, default_unit_scale),
                            page_number=page_number,
                            source_excerpt=line,
                        )
                    )
                    break

    extracted: list[ExtractedFinancialValue] = []
    for metric_key, values in candidates.items():
        if metric_key == "pat" and len(values) > 1:
            explicit_pat = [
                value
                for value in values
                if re.match(r"^(?:profit after tax|pat|net profit)\b", value.source_excerpt, re.I)
            ]
            if explicit_pat:
                values = explicit_pat
        if len(values) == 1:
            extracted.append(values[0])
        else:
            ambiguous.add(metric_key)

    if reporting_basis.casefold() == "consolidated":
        ebitda_rows: list[ExtractedFinancialValue] = []
        ebitda_pattern = re.compile(
            r"\bEBITDA\s+of\s+(?:[₹H]|\bINR\b|\bRs\.?)\s*"
            r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crores?)\b",
            re.I,
        )
        for page_number, text in pages:
            if (
                "consolidated revenues" not in text.casefold()
                or (str(end_year) not in text and target_range not in text)
            ):
                continue
            for match in ebitda_pattern.finditer(text):
                ebitda_rows.append(
                    ExtractedFinancialValue(
                        metric_key="ebitda",
                        value=Decimal(match.group("value").replace(",", "")),
                        currency="INR",
                        unit_scale="crore",
                        page_number=page_number,
                        source_excerpt=match.group(0),
                    )
                )
        ebitda_rows = list(
            {
                (item.page_number, item.value, item.source_excerpt): item
                for item in ebitda_rows
            }.values()
        )
        if len(ebitda_rows) == 1:
            extracted = [item for item in extracted if item.metric_key != "ebitda"]
            extracted.append(ebitda_rows[0])
        elif len(ebitda_rows) > 1:
            ambiguous.add("ebitda")
            extracted = [item for item in extracted if item.metric_key != "ebitda"]

    return tuple(sorted(extracted, key=lambda value: value.metric_key)), tuple(sorted(ambiguous))


def persist_document_financials(
    session: Session,
    *,
    document: Document,
    period_label: str,
    period_start: date,
    period_end: date,
    period_type: str,
    reporting_basis: str,
    currency: str,
    unit_scale: str,
) -> FinancialExtractionOutcome:
    if not document.is_primary_source or document.synthetic:
        raise ValueError("Financial extraction requires a non-synthetic primary-source document.")
    if document.ingestion_status not in {"extracted", "embedded"}:
        raise ValueError("The primary document must be ingested before financial extraction.")
    if period_type not in {"quarter", "year"}:
        raise ValueError("period_type must be quarter or year.")
    if reporting_basis not in {"standalone", "consolidated"}:
        raise ValueError("reporting_basis must be standalone or consolidated.")
    if period_end < period_start:
        raise ValueError("period_end must not precede period_start.")
    if document.period_label and document.period_label != period_label:
        raise ValueError("The requested period does not match the extracted document period.")

    chunks = session.execute(
        select(DocumentChunk.page_start, DocumentChunk.section, DocumentChunk.text)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    if not chunks:
        raise ValueError("The primary document has no extracted text chunks.")
    page_text: dict[int, list[str]] = {}
    for page_number, section, text in chunks:
        page_part = f"{section}\n{text}" if section else text
        page_text.setdefault(page_number or 1, []).append(page_part)
    pages = [
        (page_number, "\n".join(texts))
        for page_number, texts in sorted(page_text.items())
    ]
    extracted, ambiguous = extract_financial_values(
        pages,
        currency=currency,
        default_unit_scale=unit_scale,
        period_label=period_label,
        reporting_basis=reporting_basis,
    )
    incompatible_currencies = sorted(
        {item.currency for item in extracted if item.currency != currency.upper()}
    )
    if incompatible_currencies:
        raise ValueError(
            "The extracted financial rows contain currencies that do not match "
            f"the requested statement currency: {', '.join(incompatible_currencies)}."
        )

    period = session.scalar(
        select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.company_id == document.company_id,
            FinancialStatementPeriod.document_id == document.id,
            FinancialStatementPeriod.period_label == period_label,
            FinancialStatementPeriod.reporting_basis == reporting_basis,
        )
    )
    if period is None:
        fiscal_match = re.search(
            r"\bFY\s*['’]?(20\d{2})\s*[-–/]\s*(\d{2,4})",
            period_label,
            re.I,
        )
        fiscal_year = str(period_end.year)
        if fiscal_match:
            end_part = fiscal_match.group(2)
            fiscal_year = (
                f"{fiscal_match.group(1)[:2]}{end_part}"
                if len(end_part) == 2
                else end_part
            )
        period = FinancialStatementPeriod(
            company_id=document.company_id,
            document_id=document.id,
            fiscal_year=fiscal_year,
            period_label=period_label,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            reporting_basis=reporting_basis,
            currency=currency.upper(),
            unit_scale=unit_scale,
            is_synthetic=False,
        )
        session.add(period)
        session.flush()
    elif (
        period.period_start != period_start
        or period.period_end != period_end
        or period.period_type != period_type
        or period.currency.upper() != currency.upper()
        or period.unit_scale.casefold() != unit_scale.casefold()
    ):
        raise ValueError("Existing period metadata conflicts with the extraction request.")

    for value in extracted:
        existing = session.scalar(
            select(FinancialMetric).where(
                FinancialMetric.statement_period_id == period.id,
                FinancialMetric.metric_key == value.metric_key,
                FinancialMetric.reporting_basis == reporting_basis,
            )
        )
        if existing is None:
            existing = FinancialMetric(
                statement_period_id=period.id,
                document_id=document.id,
                metric_key=value.metric_key,
                reported_value=value.value,
                currency=value.currency,
                unit_scale=value.unit_scale,
                reporting_basis=reporting_basis,
                source_page=value.page_number,
                source_excerpt=value.source_excerpt,
                extraction_method="unique_line_item_v1",
                confidence=None,
                is_synthetic=False,
            )
            session.add(existing)
        elif existing.extraction_method == "unique_line_item_v1":
            existing.reported_value = value.value
            existing.currency = value.currency
            existing.unit_scale = value.unit_scale
            existing.source_page = value.page_number
            existing.source_excerpt = value.source_excerpt
    session.flush()
    return FinancialExtractionOutcome(period.id, extracted, ambiguous)


__all__ = [
    "ExtractedFinancialValue",
    "FinancialExtractionOutcome",
    "extract_financial_values",
    "persist_document_financials",
]
