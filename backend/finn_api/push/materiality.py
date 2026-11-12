from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal


CATEGORY_POINTS = {
    "results": 24,
    "M&A": 30,
    "fund_raise": 18,
    "management_change": 28,
    "litigation": 26,
    "insider_trading": 20,
    "earnings_call": 10,
    "investor_meetings": 6,
    "credit_rating": 22,
    "dividend": 14,
    "bonus_split": 12,
    "capex": 20,
    "press_release": 9,
    "postal_ballot": 7,
    "agm_egm": 7,
    "pledging": 24,
    "unclassified": 0,
}

AMOUNT_PATTERN = re.compile(
    r"(?P<currency>₹|INR|Rs\.?)?\s*"
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>crores?|cr\b|lakhs?|lacs?|million|mn\b|billions?|bn\b)",
    re.IGNORECASE,
)
FOREIGN_CURRENCY_PATTERN = re.compile(
    r"(?:USD|US\$|EUR|GBP|CAD|AUD|\$|€|£)\s*$"
    r"|^\s*(?:USD|US\$|EUR|GBP|CAD|AUD|\$|€|£)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MaterialityAssessment:
    score: int
    priority: str
    reasons: tuple[str, ...]


def priority_for_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _largest_amount_in_crore(text: str) -> tuple[Decimal, str | None] | None:
    factors = {
        "crore": Decimal("1"),
        "cr": Decimal("1"),
        "lakh": Decimal("0.01"),
        "lac": Decimal("0.01"),
        "million": Decimal("0.1"),
        "mn": Decimal("0.1"),
        "billion": Decimal("100"),
        "bn": Decimal("100"),
    }
    amounts: list[tuple[Decimal, str | None]] = []
    for match in AMOUNT_PATTERN.finditer(text):
        prefix = text[max(0, match.start() - 12) : match.start()]
        suffix = text[match.end() : match.end() + 12]
        if FOREIGN_CURRENCY_PATTERN.search(prefix) or FOREIGN_CURRENCY_PATTERN.search(
            suffix
        ):
            continue
        value = Decimal(match.group("value").replace(",", ""))
        unit = match.group("unit").casefold().rstrip("s")
        currency = match.group("currency")
        currency_label = (
            "INR"
            if currency and currency.casefold() in {"inr", "rs", "rs."}
            else "INR"
            if currency == "₹"
            else None
        )
        amounts.append((value * factors[unit], currency_label))
    return max(amounts, key=lambda item: item[0]) if amounts else None


def assess_materiality(
    *,
    category: str,
    headline: str,
    body: str | None,
    is_portfolio_company: bool,
) -> MaterialityAssessment:
    text = f"{headline} {body or ''}"
    points = CATEGORY_POINTS.get(category, 0)
    reasons = [f"Category '{category}' contributes {points} points under the published category rules."]
    score = points

    amount = _largest_amount_in_crore(text)
    if amount is None:
        reasons.append(
            "No eligible amount with a recognized unit was found; no size points added."
        )
    else:
        amount_value, currency = amount
        amount_points = 40 if amount_value >= 1000 else 30 if amount_value >= 100 else 20 if amount_value >= 10 else 10 if amount_value >= 1 else 0
        score += amount_points
        currency_text = f"{currency} " if currency else ""
        reasons.append(
            f"Largest explicit amount is approximately {currency_text}{format(amount_value.normalize(), 'f')} crore-units; "
            f"the disclosed-size band adds {amount_points} points."
        )

    lowered = text.casefold()
    modifiers: list[str] = []
    if category == "credit_rating" and re.search(r"\b(downgrad|negative outlook|rating watch)\w*\b", lowered):
        score += 12
        modifiers.append("A downgrade/negative-outlook signal adds 12 points.")
    if category == "litigation" and re.search(r"\b(penalt|fine|adverse order|restructur|insolvenc)\w*\b", lowered):
        score += 8
        modifiers.append("An adverse order, penalty, or insolvency signal adds 8 points.")
    if category == "pledging" and re.search(r"\b(increas|additional|creation|invocation)\w*\b", lowered):
        score += 8
        modifiers.append("An increased/created/invoked pledge signal adds 8 points.")
    if modifiers:
        reasons.extend(modifiers)
    else:
        reasons.append("No category-specific adverse modifier matched.")

    if is_portfolio_company:
        score += 15
        reasons.append("The issuer is in the monitored portfolio; portfolio relevance adds 15 points.")
    else:
        reasons.append("The issuer is outside the monitored portfolio; no portfolio-relevance points added.")

    bounded_score = min(100, max(0, score))
    reasons.append(
        f"Priority '{priority_for_score(bounded_score)}' follows fixed score bands: "
        "Critical 80–100, High 60–79, Medium 35–59, Low 0–34."
    )
    return MaterialityAssessment(bounded_score, priority_for_score(bounded_score), tuple(reasons))
