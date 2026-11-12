from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finn_api.config import get_settings
from finn_api.db.models import (
    Alert,
    AlertRule,
    Company,
    CompanyAlias,
    CopilotConversation,
    CopilotMessage,
    MarketDaily,
    Portfolio,
    PortfolioCompany,
    User,
)
from finn_api.network.service import expertise_search, recommend_contacts
from finn_api.pull.answering import AnswerGenerationError, generate_grounded_answer
from finn_api.pull.financial_research import build_financial_research_report, company_for_ticker
from finn_api.pull.providers import ModelProviderError, OpenAICompatibleProvider
from finn_api.pull.retrieval import DocumentRetriever, RetrievalCache
from finn_api.push.service import get_announcement_detail, get_announcement_digest
from finn_api.schemas.copilot import (
    CopilotAnswerBlock,
    CopilotCitation,
    CopilotIntent,
    CopilotLayer,
    CopilotToolResult,
)

CopilotLayerName = Literal["push", "pull", "network"]
_TICKER = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9&-]{1,19})(?:\.NS)?(?![A-Z0-9])")
_EXECUTIVE = re.compile(
    r"\b(?:new\s+)?(?:chief\s+financial\s+officer|cfo|managing\s+director|md|"
    r"chief\s+executive\s+officer|ceo|executive)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.I,
)
_GENERIC_TERMS = {
    "who", "what", "why", "how", "which", "show", "find", "tell", "analyse",
    "analyze", "company", "portfolio", "today", "important", "announcements",
    "network", "contact", "contacts", "sector", "understands", "understand",
    "worked", "works", "experience", "experienced", "could", "introduce",
    "executive", "cfo", "ceo", "md", "new", "joined", "join", "company's",
    "developments", "explain", "context", "researching", "research", "this",
    "that", "my", "in", "at", "the", "for", "me", "and", "with", "have",
}

_retrieval_cache = RetrievalCache(ttl_seconds=300)


@dataclass(frozen=True)
class IntentPlan:
    intent: CopilotIntent
    layers: tuple[CopilotLayerName, ...]
    ticker: str | None
    executive: str | None
    expertise: str | None
    needs_company: bool


def _contains(query: str, *terms: str) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", query, re.I) for term in terms)


def _expertise_term(query: str) -> str | None:
    patterns = (
        r"(?:understands?|expert(?:ise)?\s+in|experience\s+in|worked\s+in)\s+"
        r"(?:the\s+)?([a-z][a-z &/-]{2,60}?)(?:\s+sector\b|\s+industry\b|\s+experience\b|[?.!,]|$)",
        r"(?:manufacturing|banking|financial services|pharma(?:ceuticals)?|"
        r"specialty chemicals|energy|technology|infrastructure|consumer|automotive)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, query, re.I)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            cleaned = " ".join(
                token for token in value.split() if token.casefold() not in _GENERIC_TERMS
            ).strip(" ?.,!")
            if cleaned:
                return cleaned
    return None


def classify_query(query: str, *, session: Session | None = None) -> IntentPlan:
    """Map a bounded natural-language request to fixed product capabilities."""
    text = " ".join(query.split())
    lowered = text.casefold()
    ticker = _resolve_ticker(text, session) if session else None
    executive_match = _EXECUTIVE.search(text)
    executive = executive_match.group(1).strip() if executive_match else None
    expertise = _expertise_term(text)

    cross_executive = (
        _contains(lowered, "network", "who") and
        _contains(lowered, "cfo", "ceo", "executive", "joined", "know them", "introduce")
    )
    cross_company = (
        _contains(lowered, "context", "explain", "who can", "network") and
        _contains(lowered, "announcement", "developments", "researching")
    )
    if cross_executive:
        return IntentPlan("network_executive_diligence", ("push", "network"), ticker, executive, None, True)
    if cross_company and ticker:
        return IntentPlan("cross_company_context", ("push", "pull", "network"), ticker, executive, None, True)
    if _contains(lowered, "portfolio companies", "portfolio") and _contains(
        lowered, "developments", "announcements", "explain"
    ):
        return IntentPlan("cross_portfolio_context", ("push", "network"), None, None, expertise, False)
    if _contains(lowered, "unusual volume", "volume movement", "volume movements", "volume spike"):
        return IntentPlan("push_market_movement", ("push",), ticker, None, None, False)
    if _contains(lowered, "alert") and _contains(lowered, "why", "trigger", "triggered", "reason"):
        return IntentPlan("push_alert_explanation", ("push",), ticker, None, None, False)
    if _contains(lowered, "announcement", "announcements", "happened", "developments", "important"):
        return IntentPlan("push_digest", ("push",), ticker, None, None, False)
    if _contains(lowered, "network", "contact", "contacts", "introduce", "worked at", "who has worked"):
        if executive or _contains(lowered, "cfo", "ceo", "executive", "joined"):
            return IntentPlan("network_executive_diligence", ("network",), ticker, executive, expertise, True)
        if expertise:
            return IntentPlan("network_expertise", ("network",), ticker, None, expertise, False)
        return IntentPlan("network_company_connections", ("network",), ticker, None, None, True)
    if _contains(lowered, "guidance", "promise", "promised", "deliver", "delivered", "management"):
        return IntentPlan("pull_guidance", ("pull",), ticker, None, None, True)
    if _contains(lowered, "cash flow", "cashflows", "cash conversion", "profits"):
        return IntentPlan("pull_cash_quality", ("pull",), ticker, None, None, True)
    if _contains(lowered, "risk", "risks", "bear", "downside"):
        return IntentPlan("pull_financial_risks", ("pull",), ticker, None, None, True)
    if _contains(lowered, "revenue", "financial trajectory", "last four quarters", "changed"):
        return IntentPlan("pull_financial_trajectory", ("pull",), ticker, None, None, True)
    if _contains(lowered, "analyse", "analyze", "research", "financial", "company"):
        return IntentPlan("pull_research", ("pull",), ticker, None, None, True)
    return IntentPlan("unsupported", (), ticker, None, expertise, False)  # type: ignore[arg-type]


def _resolve_ticker(query: str, session: Session | None) -> str | None:
    if session is None:
        return None
    rows = session.execute(
        select(CompanyAlias.normalized_symbol, Company.display_name, Company.legal_name)
        .join(Company, Company.id == CompanyAlias.company_id)
        .where(CompanyAlias.exchange == "NSE")
    ).all()
    lowered = query.casefold()
    matches = [
        (len(name), ticker)
        for ticker, display, legal in rows
        for name in (ticker, display, legal)
        if name and (name.casefold() in lowered or (name == ticker and re.search(
            rf"(?<![A-Z0-9]){re.escape(ticker)}(?:\.NS)?(?![A-Z0-9])",
            query,
            re.I,
        )))
    ]
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    match = _TICKER.search(query.upper())
    if match:
        candidate = match.group(1).removesuffix(".NS")
        known = {row[0] for row in rows}
        if candidate in known:
            return candidate
    return None


def _citation_from_source(
    source: dict,
    *,
    ticker: str | None,
    source_type: Literal["filing", "research_document"] = "research_document",
) -> CopilotCitation:
    return CopilotCitation(
        source_type=source_type,
        title=str(source.get("document_name") or "Primary source"),
        source_url=source.get("source_url"),
        ticker=ticker,
        reporting_period=source.get("reporting_period"),
        page_number=source.get("page_number"),
        quote=source.get("quote"),
        is_synthetic=bool(source.get("is_synthetic", False)),
    )


def _section_claims(section: dict) -> list[dict]:
    return [
        claim
        for key in ("facts", "calculations", "interpretations")
        for claim in section.get(key, [])
        if isinstance(claim, dict)
    ]


def _report_block(
    ticker: str,
    report: dict,
    section_key: str,
    heading: str,
) -> CopilotAnswerBlock:
    section = report.get(section_key) or {}
    claims = _section_claims(section)
    citations: list[CopilotCitation] = []
    seen: set[tuple[str, int | None]] = set()
    summaries: list[str] = []
    for claim in claims:
        if claim.get("text"):
            summaries.append(str(claim["text"]))
        for source in claim.get("citations", []):
            key = (str(source.get("source_url")), source.get("page_number"))
            if key not in seen:
                seen.add(key)
                citations.append(_citation_from_source(source, ticker=ticker))
    available = section.get("status", "unavailable") != "unavailable" and bool(claims)
    message = " ".join(summaries[:5]) if available else (
        "No cited primary-source evidence is currently available for this dimension."
    )
    return CopilotAnswerBlock(
        layer="pull",
        heading=heading,
        summary=message,
        data={
            "status": section.get("status", "unavailable"),
            "facts": section.get("facts", []),
            "calculations": section.get("calculations", []),
            "interpretations": section.get("interpretations", []),
            "observations": section.get("observations", []),
            "limitations": section.get("limitations", []),
            "company": report.get("company_name"),
            "ticker": ticker,
            "is_synthetic": report.get("is_synthetic", False),
        },
        citations=citations,
    )


def _network_block(result, heading: str) -> CopilotAnswerBlock:
    recommendations = getattr(result, "recommendations", [])
    people = [
        {
            "id": str(item.contact.id),
            "name": item.contact.display_name,
            "role": item.contact.current_role,
            "employer": item.contact.current_employer,
            "distance": item.connection_distance,
            "score": item.score,
            "reasons": item.reasons,
            "path": [
                {
                    "name": step.name,
                    "relationship_type": step.relationship_type,
                    "evidence": step.evidence,
                    "last_interaction": step.last_interaction.isoformat()
                    if step.last_interaction
                    else None,
                }
                for step in item.path
            ],
            "is_synthetic": item.contact.is_synthetic,
        }
        for item in recommendations
    ]
    citations = [
        CopilotCitation(
            source_type="relationship",
            title=f"Recorded relationship path to {person['name']}",
            quote=" → ".join(
                f"{step['name']} ({step['relationship_type']}): {step['evidence'] or 'recorded relationship'}"
                for step in person["path"]
            ),
            is_synthetic=person["is_synthetic"],
        )
        for person in people
        if person["path"] and all(step["evidence"] for step in person["path"])
    ]
    return CopilotAnswerBlock(
        layer="network",
        heading=heading,
        summary=getattr(result, "notice", None)
        or (
            f"Found {len(people)} reachable contacts with explicit relationship paths."
            if people
            else "No reachable contacts with supporting relationship evidence were found."
        ),
        data={"recommendations": people},
        citations=citations,
    )


def _announcement_block(items, heading: str) -> CopilotAnswerBlock:
    citations: list[CopilotCitation] = []
    announcements = []
    for item in items:
        announcements.append(
            {
                "id": str(item.id),
                "company": item.company_name,
                "ticker": item.ticker,
                "headline": item.headline,
                "filed_at": item.filed_at.isoformat(),
                "category": item.category,
                "summary": item.summary,
                "materiality_score": item.materiality_score,
                "priority": item.priority,
                "reasons": list(item.materiality_reasons),
                "is_synthetic": item.is_synthetic,
            }
        )
        citations.append(
            CopilotCitation(
                source_type="filing",
                title=item.headline,
                source_url=item.original_filing_url or None,
                ticker=item.ticker,
                quote=item.summary,
                is_synthetic=item.is_synthetic,
            )
        )
    summary = (
        f"Found {len(announcements)} portfolio announcements. They are ordered by materiality and filing time."
        if announcements
        else "No portfolio announcements were found in this time window."
    )
    return CopilotAnswerBlock(
        layer="push",
        heading=heading,
        summary=summary,
        data={"announcements": announcements},
        citations=citations,
    )


def _digest(session: Session, workspace_id: UUID, *, ticker: str | None, window: str):
    digest = get_announcement_digest(
        session,
        workspace_id=workspace_id,
        window=window,  # type: ignore[arg-type]
        tickers=(ticker,) if ticker else (),
    )
    return digest.items


def _market_movements(
    session: Session,
    workspace_id: UUID,
    ticker: str | None,
) -> tuple[list[dict], bool, int]:
    portfolio = session.scalar(
        select(Portfolio).where(
            Portfolio.workspace_id == workspace_id, Portfolio.is_default.is_(True)
        )
    )
    if portfolio is None:
        return [], False, 0
    volume_rules = session.scalars(
        select(AlertRule).where(
            AlertRule.workspace_id == workspace_id,
            AlertRule.portfolio_id == portfolio.id,
            AlertRule.enabled.is_(True),
            AlertRule.rule_type == "volume_move",
            AlertRule.volume_multiplier.is_not(None),
        )
    ).all()
    if not volume_rules:
        return [], False, 0
    portfolio_thresholds = [
        rule.volume_multiplier for rule in volume_rules if rule.company_id is None
    ]
    default_threshold = min(portfolio_thresholds) if portfolio_thresholds else None
    company_thresholds: dict[UUID, Decimal] = {}
    for rule in volume_rules:
        if rule.company_id is not None and rule.volume_multiplier is not None:
            company_thresholds[rule.company_id] = min(
                company_thresholds.get(rule.company_id, rule.volume_multiplier),
                rule.volume_multiplier,
            )
    ranked_market = (
        select(
            MarketDaily.id.label("market_id"),
            func.row_number()
            .over(
                partition_by=MarketDaily.company_id,
                order_by=(
                    MarketDaily.market_date.desc(),
                    MarketDaily.fetched_at.desc(),
                    MarketDaily.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .join(PortfolioCompany, PortfolioCompany.company_id == MarketDaily.company_id)
        .where(
            PortfolioCompany.portfolio_id == portfolio.id,
            MarketDaily.exchange == "NSE",
        )
    ).subquery()
    query = (
        select(MarketDaily, Company, CompanyAlias)
        .join(ranked_market, ranked_market.c.market_id == MarketDaily.id)
        .join(Company, Company.id == MarketDaily.company_id)
        .join(CompanyAlias, CompanyAlias.company_id == Company.id)
        .where(
            ranked_market.c.row_number == 1,
            CompanyAlias.exchange == "NSE",
        )
    )
    if ticker:
        query = query.where(CompanyAlias.normalized_symbol == ticker)
    rows = session.execute(
        query.order_by(MarketDaily.market_date.desc(), MarketDaily.fetched_at.desc())
    ).all()
    eligible_observations = [
        (market, company, alias, company_thresholds.get(company.id, default_threshold))
        for market, company, alias in rows
        if company_thresholds.get(company.id, default_threshold) is not None
        and market.volume_ratio is not None
    ]
    movements = [
        {
            "company": company.display_name,
            "ticker": alias.normalized_symbol,
            "date": market.market_date.isoformat(),
            "close": str(market.close),
            "daily_change_pct": str(market.daily_change_pct)
            if market.daily_change_pct is not None
            else None,
            "volume": market.volume,
            "average_volume_20": str(market.average_volume_20)
            if market.average_volume_20 is not None
            else None,
            "volume_ratio": str(market.volume_ratio)
            if market.volume_ratio is not None
            else None,
            "configured_volume_threshold": str(
                company_thresholds.get(company.id, default_threshold)
            )
            if company_thresholds.get(company.id, default_threshold) is not None
            else None,
            "source": market.source,
            "fetched_at": market.fetched_at.isoformat(),
            "is_synthetic": market.synthetic,
        }
        for market, company, alias, threshold in eligible_observations
        if threshold is not None
        and market.volume_ratio is not None
        and Decimal(market.volume_ratio) >= Decimal(threshold)
    ]
    movements = sorted(
        movements,
        key=lambda item: float(item["volume_ratio"] or 0),
        reverse=True,
    )
    return movements, True, len(eligible_observations)


def _pull_research(
    session: Session,
    *,
    ticker: str,
    query: str,
) -> tuple[dict, list[CopilotAnswerBlock], list[CopilotToolResult], list[str]]:
    try:
        company, _ = company_for_ticker(session, ticker)
        report = build_financial_research_report(
            session,
            company_id=company.id,
            ticker=ticker,
            reporting_basis="consolidated",
            quarters=4,
            persist_guidance=False,
        )
    except LookupError as error:
        return {}, [], [
            CopilotToolResult(name="financial_research", status="unavailable", message=str(error))
        ], ["The requested ticker has not been discovered in the company universe."]
    keys = {
        "pull_research": ["business_snapshot", "financial_snapshot", "financial_trajectory"],
        "pull_financial_trajectory": ["financial_trajectory"],
        "pull_guidance": ["management_guidance", "narrative_vs_numbers"],
        "pull_cash_quality": ["cash_quality_analysis", "financial_snapshot"],
        "pull_financial_risks": ["balance_sheet_analysis", "bull_vs_bear"],
    }
    return report, [], [
        CopilotToolResult(
            name="deterministic_financial_analysis",
            status="complete" if report.get("status") != "unavailable" else "partial",
            message="Financial calculations and guidance assessments were read from the deterministic research service.",
        )
    ], []


def execute_query(
    session: Session,
    *,
    workspace_id: UUID,
    query: str,
) -> tuple[IntentPlan, str, list[CopilotAnswerBlock], list[CopilotToolResult], list[str]]:
    plan = classify_query(query, session=session)
    if plan.intent == "unsupported":
        return (
            plan,
            "I can route questions about portfolio announcements and alerts, primary-source company research, financial trajectories and guidance, or evidence-backed network connections. Please include a company or NSE ticker when the question is company-specific.",
            [],
            [],
            ["No tool was called because the request did not match a supported FINN workflow."],
        )
    if plan.needs_company and not plan.ticker:
        return (
            plan,
            "Which NSE company or ticker do you mean? I need an unambiguous company before retrieving financial, announcement, or company-network context.",
            [],
            [],
            ["No company-specific tools were called because the company could not be resolved."],
        )

    blocks: list[CopilotAnswerBlock] = []
    tools: list[CopilotToolResult] = []
    limitations: list[str] = []
    ticker = plan.ticker

    if "push" in plan.layers:
        if plan.intent == "push_market_movement":
            movements, thresholds_configured, observations_with_baseline = _market_movements(
                session, workspace_id, ticker
            )
            citations = [
                CopilotCitation(
                    source_type="market_data",
                    title=f"{item['company']} EOD market data · {item['date']}",
                    ticker=item["ticker"],
                    reporting_period=item["date"],
                    quote=(
                        f"Close {item['close']}; daily move {item['daily_change_pct'] or 'unavailable'}%; "
                        f"volume ratio {item['volume_ratio'] or 'unavailable'}×; "
                        f"configured threshold {item['configured_volume_threshold']}×."
                    ),
                    is_synthetic=item["is_synthetic"],
                )
                for item in movements
            ]
            blocks.append(
                CopilotAnswerBlock(
                    layer="push",
                    heading="Unusual end-of-day volume",
                    summary=(
                        f"Found {len(movements)} latest EOD observations that meet configured workspace volume thresholds. "
                        "The comparison uses each stored 20-session baseline; these are delayed/end-of-day observations, not live intraday activity."
                        if movements
                        else "No stored end-of-day volume observation currently meets an enabled workspace threshold."
                        if observations_with_baseline
                        else "No eligible latest EOD observations with a calculated 20-session volume baseline are available."
                        if thresholds_configured
                        else "No enabled volume-movement threshold is configured for this portfolio."
                    ),
                    data={
                        "movements": movements,
                        "data_kind": "end_of_day",
                        "thresholds_configured": thresholds_configured,
                        "observations_with_baseline": observations_with_baseline,
                    },
                    citations=citations,
                )
            )
            tools.append(
                CopilotToolResult(
                    name="portfolio_market_data",
                    status=(
                        "complete"
                        if thresholds_configured and observations_with_baseline
                        else "unavailable"
                    ),
                    message=(
                        f"Matched {len(movements)} observations against configured volume thresholds."
                        if thresholds_configured and observations_with_baseline
                        else "Volume thresholds are configured, but no eligible 20-session EOD baseline is available."
                        if thresholds_configured
                        else "No enabled volume threshold is available; FINN did not apply an arbitrary anomaly cutoff."
                    ),
                )
            )
            if not thresholds_configured:
                limitations.append(
                    "Configure a volume-movement alert threshold before FINN can identify unusual volume."
                )
            elif not observations_with_baseline:
                limitations.append(
                    "No eligible latest EOD volume observation has a calculated 20-session baseline."
                )
        elif plan.intent == "push_alert_explanation":
            rows = session.scalars(
                select(Alert)
                .where(Alert.workspace_id == workspace_id)
                .order_by(Alert.created_at.desc())
                .limit(100)
            ).all()
            if ticker:
                rows = [
                    row
                    for row in rows
                    if row.company_id
                    and session.scalar(
                        select(CompanyAlias.id).where(
                            CompanyAlias.company_id == row.company_id,
                            CompanyAlias.exchange == "NSE",
                            CompanyAlias.normalized_symbol == ticker,
                        )
                    )
                ]
            details = []
            citations = []
            for row in rows[:12]:
                details.append(
                    {
                        "id": str(row.id),
                        "title": row.title,
                        "summary": row.summary,
                        "alert_type": row.alert_type,
                        "created_at": row.created_at.isoformat(),
                        "status": row.status,
                        "is_synthetic": row.is_synthetic,
                    }
                )
                citations.append(
                    CopilotCitation(
                        source_type="alert",
                        title=row.title,
                        ticker=ticker,
                        quote=row.summary,
                        is_synthetic=row.is_synthetic,
                    )
                )
                if row.announcement_id:
                    try:
                        announcement = get_announcement_detail(
                            session, row.announcement_id, workspace_id=workspace_id
                        )
                    except LookupError:
                        continue
                    citations.append(
                        CopilotCitation(
                            source_type="filing",
                            title=announcement.headline,
                            source_url=announcement.original_filing_url or None,
                            ticker=announcement.ticker,
                            quote=announcement.summary,
                            is_synthetic=announcement.is_synthetic,
                        )
                    )
            blocks.append(
                CopilotAnswerBlock(
                    layer="push",
                    heading="Alert history and trigger evidence",
                    summary=f"Found {len(details)} alert records matching the query.",
                    data={"alerts": details},
                    citations=citations,
                )
            )
            tools.append(
                CopilotToolResult(
                    name="workspace_alert_history",
                    status="complete" if details else "unavailable",
                    message=f"Read {len(details)} alert records.",
                )
            )
        else:
            window = "7d" if _contains(query.casefold(), "important", "most important") else "24h"
            items = _digest(session, workspace_id, ticker=ticker, window=window)
            blocks.append(
                _announcement_block(
                    items,
                    f"{'Important ' if window == '7d' else ''}portfolio announcements · {window}",
                )
            )
            tools.append(
                CopilotToolResult(
                    name="portfolio_announcement_digest",
                    status="complete" if items else "unavailable",
                    message=f"Read {len(items)} portfolio announcements in the {window} window.",
                )
            )
            if not items:
                limitations.append("No matching announcements were found in the selected window.")

    if "pull" in plan.layers and ticker:
        report, _, research_tools, research_limits = _pull_research(
            session, ticker=ticker, query=query
        )
        tools.extend(research_tools)
        limitations.extend(research_limits)
        section_keys = {
            "pull_research": ["business_snapshot", "financial_snapshot", "financial_trajectory"],
            "pull_financial_trajectory": ["financial_trajectory"],
            "pull_guidance": ["management_guidance", "narrative_vs_numbers"],
            "pull_cash_quality": ["cash_quality_analysis", "financial_snapshot"],
            "pull_financial_risks": ["balance_sheet_analysis", "bull_vs_bear"],
            "cross_company_context": ["financial_snapshot", "financial_trajectory", "management_guidance"],
            "network_executive_diligence": [],
        }.get(plan.intent, [])
        labels = {
            "business_snapshot": "Business snapshot",
            "financial_snapshot": "Financial snapshot",
            "financial_trajectory": "Financial trajectory",
            "management_guidance": "Management guidance",
            "narrative_vs_numbers": "Narrative versus numbers",
            "cash_quality_analysis": "Cash quality",
            "balance_sheet_analysis": "Balance-sheet analysis",
            "bull_vs_bear": "Bull and bear evidence",
        }
        for section_key in section_keys:
            if report.get(section_key):
                blocks.append(_report_block(ticker, report, section_key, labels[section_key]))
        if not section_keys and report:
            blocks.append(_report_block(ticker, report, "financial_snapshot", "Financial snapshot"))
        if plan.intent in {
            "pull_research",
            "pull_financial_trajectory",
            "pull_guidance",
            "pull_cash_quality",
            "pull_financial_risks",
            "cross_company_context",
        }:
            rag_block, rag_tool, rag_limits = _answer_from_sources(
                session, ticker=ticker, query=query
            )
            if rag_block:
                blocks.append(rag_block)
            tools.append(rag_tool)
            limitations.extend(rag_limits)

    if "network" in plan.layers:
        if plan.intent == "network_expertise":
            if not plan.expertise:
                limitations.append("Specify an expertise area or sector so network matches can be ranked.")
                tools.append(CopilotToolResult(
                    name="network_expertise_search",
                    status="unavailable",
                    message="No expertise query could be extracted.",
                ))
            else:
                contacts = expertise_search(
                    session,
                    workspace_id=workspace_id,
                    query=plan.expertise,
                    limit=50,
                )
                matching_ids = {contact.id for contact in contacts}
                result = recommend_contacts(
                    session,
                    workspace_id=workspace_id,
                    workflow="sector_expertise",
                    ticker=ticker,
                    expertise=plan.expertise,
                    limit=20,
                )
                ranked = [
                    item
                    for item in result.recommendations
                    if item.contact.id in matching_ids
                ]
                result.recommendations = ranked
                blocks.append(_network_block(result, f"Network expertise · {plan.expertise}"))
                tools.append(CopilotToolResult(
                    name="network_expertise_and_relationship_ranking",
                    status="complete" if ranked else "unavailable",
                    message=f"Retrieved {len(ranked)} contacts with explicit reachable paths.",
                ))
        elif plan.intent == "network_company_connections":
            if ticker:
                from finn_api.network.service import company_connections

                result = company_connections(session, workspace_id=workspace_id, ticker=ticker)
                people = []
                citations = []
                if result:
                    for contact in result.contacts:
                        if contact.connection_distance is None or not contact.relationship_path:
                            continue
                        people.append({
                            "name": contact.display_name,
                            "role": contact.current_role,
                            "employer": contact.current_employer,
                            "distance": contact.connection_distance,
                            "path": [
                                {
                                    "name": step.name,
                                    "relationship_type": step.relationship_type,
                                    "evidence": step.evidence,
                                }
                                for step in contact.relationship_path
                            ],
                            "is_synthetic": contact.is_synthetic,
                        })
                        citations.append(CopilotCitation(
                            source_type="relationship",
                            title=f"Company connection path to {contact.display_name}",
                            ticker=ticker,
                            quote=" → ".join(
                                f"{step.name} ({step.relationship_type}): {step.evidence or 'no evidence supplied'}"
                                for step in contact.relationship_path
                            ),
                            is_synthetic=contact.is_synthetic,
                        ))
                blocks.append(CopilotAnswerBlock(
                    layer="network",
                    heading=f"Network contacts with {ticker} work history",
                    summary=f"Found {len(people)} reachable contacts with matched company history."
                    if people else "No reachable contacts with matched company work history were found.",
                    data={"contacts": people},
                    citations=citations,
                ))
                tools.append(CopilotToolResult(
                    name="company_network_connections",
                    status="complete" if people else "unavailable",
                    message=f"Retrieved {len(people)} contacts with explicit relationship paths.",
                ))
            else:
                limitations.append("Specify an NSE company or ticker for a company-network search.")
        elif plan.intent == "network_executive_diligence":
            if not ticker:
                limitations.append("Specify the NSE company whose incoming executive you want to diligence.")
            else:
                result = recommend_contacts(
                    session,
                    workspace_id=workspace_id,
                    workflow="management_diligence",
                    ticker=ticker,
                    executive=plan.executive,
                    limit=20,
                )
                blocks.append(_network_block(result, f"Network context for {ticker} management"))
                tools.append(CopilotToolResult(
                    name="management_change_and_network_match",
                    status="complete" if result.recommendations else "unavailable",
                    message=f"Returned {len(result.recommendations)} evidence-backed management-diligence matches.",
                ))
                if not result.recommendations:
                    limitations.append("No supported management-change-to-contact match was found.")
        elif plan.intent in {"cross_portfolio_context", "cross_company_context"}:
            if ticker:
                result = recommend_contacts(
                    session,
                    workspace_id=workspace_id,
                    workflow="who_to_call",
                    ticker=ticker,
                    expertise=plan.expertise,
                    limit=10,
                )
                blocks.append(_network_block(result, f"Reachable context providers · {ticker}"))
                tools.append(CopilotToolResult(
                    name="company_network_context",
                    status="complete" if result.recommendations else "unavailable",
                    message=f"Retrieved {len(result.recommendations)} contacts with explicit reachable paths.",
                ))
            else:
                items = _digest(session, workspace_id, ticker=None, window="24h")
                by_ticker: dict[str, list] = {}
                for item in items[:10]:
                    by_ticker.setdefault(item.ticker, [])
                    if item.category == "management_change":
                        result = recommend_contacts(
                            session,
                            workspace_id=workspace_id,
                            workflow="management_diligence",
                            ticker=item.ticker,
                            limit=5,
                        )
                    else:
                        result = recommend_contacts(
                            session,
                            workspace_id=workspace_id,
                            workflow="who_to_call",
                            ticker=item.ticker,
                            limit=5,
                        )
                    by_ticker[item.ticker].extend(result.recommendations)
                recommendations = [
                    item
                    for values in by_ticker.values()
                    for item in values
                ]
                unique = {item.contact.id: item for item in recommendations}
                if recommendations:
                    from finn_api.schemas.network import NetworkRecommendationsResponse

                    network_result = NetworkRecommendationsResponse(
                        workflow="who_to_call",
                        ticker=None,
                        executive=None,
                        recommendations=list(unique.values())[:20],
                        notice="Contacts are included only when the Network service returns an explicit relationship path.",
                    )
                else:
                    network_result = recommend_contacts(
                        session,
                        workspace_id=workspace_id,
                        workflow="who_to_call",
                        limit=1,
                    )
                blocks.append(_network_block(
                    network_result,
                    "Reachable contacts for portfolio developments",
                ))
                tools.append(CopilotToolResult(
                    name="portfolio_company_network_context",
                    status="complete" if unique else "unavailable",
                    message=f"Matched reachable contacts to {len(by_ticker)} companies with announcements.",
                ))

    if not blocks:
        answer = "FINN could not produce an evidence-backed result for this request."
    elif plan.intent in {"cross_portfolio_context", "cross_company_context", "network_executive_diligence"}:
        answer = "I routed this request across the relevant FINN layers. The sections below contain only retrieved filings, deterministic analysis, and workspace relationship records."
    elif plan.intent == "push_market_movement":
        answer = "These are the latest stored end-of-day portfolio observations, ranked by volume ratio. They are not live market data."
    elif plan.intent.startswith("network"):
        answer = "These contacts were returned by the workspace Network service. Each recommendation includes its recorded path and supporting relationship evidence."
    elif plan.intent.startswith("push"):
        answer = "This result comes from the portfolio announcement or alert records; materiality explanations and original filings are shown with the relevant items."
    else:
        answer = "The research sections below use deterministic financial analysis and primary-source evidence. Unsupported or missing facts are called out rather than inferred."
    return plan, answer, blocks, tools, list(dict.fromkeys(limitations))


def _answer_from_sources(
    session: Session,
    *,
    ticker: str,
    query: str,
) -> tuple[CopilotAnswerBlock | None, CopilotToolResult, list[str]]:
    from finn_api.api.research import _provider

    provider = _provider()
    try:
        company, _ = company_for_ticker(session, ticker)
        retriever = DocumentRetriever(
            embedding_provider=provider,
            cache=_retrieval_cache,
            max_context_chars=get_settings().research_max_context_chars,
        )
        evidence = retriever.retrieve(
            session,
            company_id=company.id,
            ticker=ticker,
            query=query,
            document_types=(
                "annual_report",
                "quarterly_result",
                "earnings_call_transcript",
                "investor_presentation",
            ),
            top_k=8,
            include_synthetic=False,
        )
        grounded = generate_grounded_answer(
            ticker=ticker,
            question=query,
            evidence=evidence,
            research_model=provider,
        )
    except (LookupError, ModelProviderError, AnswerGenerationError) as error:
        return None, CopilotToolResult(
            name="primary_source_rag",
            status="unavailable",
            message=str(error),
        ), ["Primary-source RAG could not return a validated answer."]
    finally:
        if provider:
            provider.close()
    citations = [
        CopilotCitation(
            source_type="research_document",
            title=citation.document_name,
            source_url=citation.source_url,
            ticker=ticker,
            reporting_period=citation.reporting_period,
            page_number=citation.page_number,
            quote=citation.quote,
            is_synthetic=citation.is_synthetic,
        )
        for claim in grounded.claims
        for citation in claim.citations
    ]
    citations = list({
        (item.title, item.page_number, item.source_url, item.quote): item
        for item in citations
    }.values())
    summary = " ".join(claim.text for claim in grounded.claims) if grounded.claims else (
        "No relevant primary-source passages were retrieved. FINN cannot answer this from unsupported sources or model memory."
    )
    block = CopilotAnswerBlock(
        layer="pull",
        heading="Primary-source answer",
        summary=summary,
        data={
            "status": grounded.status,
            "claims": [claim.model_dump(mode="json") for claim in grounded.claims],
            "source_count": grounded.source_count,
            "model_route": grounded.model_route,
            "is_synthetic": grounded.is_synthetic,
            "limitations": grounded.limitations,
        },
        citations=citations,
    )
    return block, CopilotToolResult(
        name="primary_source_rag",
        status="complete" if grounded.claims else "unavailable",
        message=f"Validated {len(grounded.claims)} claims against {grounded.source_count} primary documents.",
    ), list(grounded.limitations)


def save_exchange(
    session: Session,
    *,
    user: User,
    workspace_id: UUID,
    query: str,
    conversation_id: UUID | None,
    response_data: dict,
) -> tuple[CopilotConversation, CopilotMessage]:
    conversation = None
    if conversation_id:
        conversation = session.scalar(
            select(CopilotConversation).where(
                CopilotConversation.id == conversation_id,
                CopilotConversation.workspace_id == workspace_id,
                CopilotConversation.user_id == user.id,
            )
        )
        if conversation is None:
            raise LookupError("Conversation was not found for this user and workspace.")
        conversation.updated_at = datetime.now(timezone.utc)
    else:
        conversation = CopilotConversation(
            workspace_id=workspace_id,
            user_id=user.id,
            title=query[:200],
        )
        session.add(conversation)
        session.flush()
    exchange_time = datetime.now(timezone.utc)
    session.add(
        CopilotMessage(
            conversation_id=conversation.id,
            role="user",
            content=query,
            created_at=exchange_time,
        )
    )
    assistant = CopilotMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=str(response_data.get("answer", "")),
        result=response_data,
        created_at=exchange_time + timedelta(microseconds=1),
    )
    session.add(assistant)
    session.flush()
    return conversation, assistant
