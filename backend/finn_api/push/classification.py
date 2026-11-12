from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryRule:
    category: str
    patterns: tuple[re.Pattern[str], ...]


def _rule(category: str, *patterns: str) -> CategoryRule:
    return CategoryRule(
        category,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns),
    )


CATEGORY_RULES = (
    _rule("pledging", r"\bpromoter.{0,40}\bpledg", r"\bpledged shares?\b", r"\bpledge.{0,30}(release|invoke|creation|invocation)"),
    _rule("management_change", r"\b(appoint(?:ment|ed)?|resign(?:ation|ed)?|retir(?:ement|ed)|cessation|join(?:s|ed)?)\b.{0,80}\b(ceo|cfo|chief|managing director|md|director|key managerial|senior leadership|leadership)\b", r"\b(ceo|cfo|chief executive|chief financial|managing director|whole[- ]time director|senior leadership|leadership)\b.{0,80}\b(appoint(?:ment|ed)?|resign(?:ation|ed)?|retir(?:ement|ed)|cessation|join(?:s|ed)?)\b"),
    _rule("litigation", r"\b(litigat\w*|lawsuit|legal proceeding|court order|regulatory order|show cause|penalt\w*|fine|insolvency|restructur\w*|winding[- ]up)\b"),
    _rule("credit_rating", r"\b(credit rating|rating agency|rating outlook|rating downgrad\w*|rating upgrad\w*|rating reaffirm\w*)\b"),
    _rule("M&A", r"\b(acqui(sition|re)|merger|demerger|joint venture|jointly controlled|stake (purchase|sale|acquisition)|subsidiary investment)\b"),
    _rule("fund_raise", r"\b(rights issue|qip\b|qualified institutional placement|preferential allotment|commercial paper|debt issue|fund rais(?:e|ing)|capital rais(?:e|ing)|buyback|buy-back)\b"),
    _rule("insider_trading", r"\binsider trading disclosure\b", r"\b(insider|promoter|designated person).{0,80}\b(buy|buys|bought|purchase|purchased|sale|sold|traded|disposal|acquisition of shares)\b", r"\b(substantial acquisition|shareholding disclosure|trading window)\b"),
    _rule("capex", r"\b(capex|capital expenditure|new plant|new facility|capacity expansion|manufacturing facility|manufacturing investment|project expenditure)\b"),
    _rule("bonus_split", r"\b(bonus issue|stock split|share split|share subdivision|sub(?:-| )?division of (equity )?shares|split of equity shares)\b"),
    _rule("dividend", r"\b(interim dividend|final dividend|dividend (?:recommendation|recommended|declared|proposal|per share)|record date.{0,40}dividend)\b"),
    _rule("results", r"\b(quarterly results?|financial results?|annual results?|audited results?|unaudited results?|results for the quarter|board meeting.{0,50}results)\b"),
    _rule("earnings_call", r"\b(earnings call|investor conference call|analyst call|concall|conference call|call transcript|webcast link)\b"),
    _rule("investor_meetings", r"\b(investor (meet|meeting|conference)|analyst meet|one[- ]on[- ]one meeting|group meeting)\b"),
    _rule("postal_ballot", r"\b(postal ballot|e-voting|remote e-voting)\b"),
    _rule("agm_egm", r"\b(annual general meeting|extraordinary general meeting|\bagm\b|\begm\b)\b"),
    _rule("press_release", r"\b(press release|order win|new product|product launch|business update|rumou?r clarification|partnership announcement)\b"),
)

CATEGORY_KEYS = (
    "results",
    "M&A",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
)


@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    matched_terms: tuple[str, ...]


def classify_announcement(headline: str, body: str | None = None) -> Classification:
    text = " ".join(part.strip() for part in (headline, body or "") if part.strip())
    for rule in CATEGORY_RULES:
        hits = tuple(
            match.group(0)
            for pattern in rule.patterns
            for match in pattern.finditer(text)
        )
        if hits:
            confidence = min(0.99, 0.82 + 0.06 * (len(hits) - 1))
            return Classification(rule.category, confidence, hits[:5])
    return Classification("unclassified", 0.55, ())


def summarize_announcement(headline: str, body: str | None) -> str:
    text = re.sub(r"\s+", " ", (body or "").strip())
    if not text:
        return headline.strip()
    if text.casefold().startswith(headline.strip().casefold()):
        return text[:360]
    return f"{headline.strip()} — {text}"[:360]
