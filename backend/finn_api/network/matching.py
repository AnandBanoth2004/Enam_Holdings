from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_COMPANY_SUFFIXES = {
    "limited",
    "ltd",
    "private",
    "pvt",
    "company",
    "co",
    "corporation",
    "corp",
    "plc",
}


def normalize_entity_name(value: str) -> str:
    return " ".join(_NON_ALPHANUMERIC.sub(" ", value.casefold()).split())


def normalize_company_name(value: str) -> str:
    tokens = normalize_entity_name(value).split()
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _token_similarity(left: str, right: str) -> float:
    left_tokens = left.split()
    right_tokens = right.split()
    if not left_tokens or not right_tokens:
        return 0.0
    matched = sum(
        1
        for token in left_tokens
        if max(
            (SequenceMatcher(None, token, candidate).ratio() for candidate in right_tokens),
            default=0.0,
        )
        >= 0.9
    )
    return matched / max(len(left_tokens), len(right_tokens))


@dataclass(frozen=True)
class EntityCandidate:
    candidate_id: str
    display_name: str


@dataclass(frozen=True)
class EntityCandidateMatch:
    candidate_id: str
    display_name: str
    confidence: float
    method: str


def match_contact_name(
    query: str,
    candidates: list[EntityCandidate],
    *,
    minimum_fuzzy_confidence: float = 0.96,
) -> list[EntityCandidateMatch]:
    normalized_query = normalize_entity_name(query)
    if not normalized_query:
        return []
    exact = [
        EntityCandidateMatch(item.candidate_id, item.display_name, 1.0, "exact")
        for item in candidates
        if normalize_entity_name(item.display_name) == normalized_query
    ]
    if exact:
        return exact

    query_tokens = normalized_query.split()
    matches: list[EntityCandidateMatch] = []
    for candidate in candidates:
        normalized_candidate = normalize_entity_name(candidate.display_name)
        candidate_tokens = normalized_candidate.split()
        if len(query_tokens) < 2 or len(candidate_tokens) < 2:
            continue
        confidence = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
        token_overlap = _token_similarity(normalized_query, normalized_candidate)
        if confidence >= minimum_fuzzy_confidence and token_overlap >= 0.8:
            matches.append(
                EntityCandidateMatch(
                    candidate.candidate_id,
                    candidate.display_name,
                    round(confidence, 4),
                    "fuzzy_proposed",
                )
            )
    return sorted(matches, key=lambda item: (-item.confidence, item.display_name))


def score_contact_relevance(
    contact_expertise: list[str],
    contact_industries: list[str],
    contact_employers: list[str],
    *,
    target_company: str | None = None,
    target_sector: str | None = None,
    target_executive: str | None = None,
    connection_distance: int = 1,
    relationship_strength: str = "",
) -> tuple[int, list[str]]:
    """
    Rank a contact by relevance to a specific investment context.

    Returns (score, reasons) where score is 0-100 and reasons is a
    list of human-readable explanation strings.

    Rules:
    - Connection distance: 1st degree +20pts, 2nd degree +10pts
    - Relationship strength: strong +15, moderate +8, light +3
    - Employer match: exact portfolio company +35pts
    - Sector match: same sector +18pts
    - Expertise query match: +25pts
    - Executive name match: up to +35pts (scaled by confidence)

    Career overlap alone does NOT score relationship points.
    """
    score = 0
    reasons: list[str] = []

    # Connection distance
    if connection_distance == 1:
        score += 20
        reasons.append("Reachable via an explicitly recorded first-degree relationship.")
    elif connection_distance == 2:
        score += 10
        reasons.append("Reachable via an explicitly recorded second-degree path.")

    # Relationship strength
    strength_scores = {"strong": 15, "moderate": 8, "light": 3}
    score += strength_scores.get(relationship_strength.lower().strip(), 2)

    # Employer/company match
    if target_company:
        normalized_target = normalize_company_name(target_company)
        for employer in contact_employers:
            if normalize_company_name(employer) == normalized_target:
                score += 35
                reasons.append(
                    f"Career history includes {employer}; this is expertise context, "
                    "not proof of a personal relationship."
                )
                break
        else:
            # Partial sector match
            if target_sector:
                target_sector_key = target_sector.casefold()
                sector_matches = [ind for ind in contact_industries if target_sector_key in ind.casefold()]
                if sector_matches:
                    score += 18
                    reasons.append(f"Profile includes experience in '{target_sector}'.")

    return min(score, 100), reasons


def match_executive_to_contacts(
    executive_name: str,
    contact_candidates: list[EntityCandidate],
    *,
    minimum_fuzzy_confidence: float = 0.96,
) -> list[EntityCandidateMatch]:
    """
    Match an incoming executive name against network contacts.
    Returns matches sorted by confidence descending.
    Does NOT assert the person knows anybody; it only identifies possible
    name matches for human confirmation.
    """
    return match_contact_name(
        executive_name,
        contact_candidates,
        minimum_fuzzy_confidence=minimum_fuzzy_confidence,
    )


def match_company_name(
    query: str,
    candidates: list[EntityCandidate],
    *,
    minimum_fuzzy_confidence: float = 0.94,
) -> list[EntityCandidateMatch]:
    normalized_query = normalize_company_name(query)
    if not normalized_query:
        return []
    exact = [
        EntityCandidateMatch(item.candidate_id, item.display_name, 1.0, "exact")
        for item in candidates
        if normalize_company_name(item.display_name) == normalized_query
    ]
    if exact:
        return exact

    if len(normalized_query.split()) < 2:
        return []
    matches = []
    for candidate in candidates:
        normalized_candidate = normalize_company_name(candidate.display_name)
        token_overlap = _token_similarity(normalized_query, normalized_candidate)
        confidence = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
        if confidence >= minimum_fuzzy_confidence and token_overlap >= 0.8:
            matches.append(
                EntityCandidateMatch(
                    candidate.candidate_id,
                    candidate.display_name,
                    round(confidence, 4),
                    "fuzzy_proposed",
                )
            )
    return sorted(matches, key=lambda item: (-item.confidence, item.display_name))


def score_contact_relevance(
    contact_expertise: list[str],
    contact_industries: list[str],
    contact_employers: list[str],
    *,
    target_company: str | None = None,
    target_sector: str | None = None,
    target_executive: str | None = None,
    connection_distance: int = 1,
    relationship_strength: str = "",
) -> tuple[int, list[str]]:
    """
    Rank a contact by relevance to a specific investment context.

    Returns (score, reasons) where score is 0-100 and reasons is a
    list of human-readable explanation strings.

    Rules:
    - Connection distance: 1st degree +20pts, 2nd degree +10pts
    - Relationship strength: strong +15, moderate +8, light +3
    - Employer match: exact portfolio company +35pts
    - Sector match: same sector +18pts
    - Expertise query match: +25pts
    - Executive name match: up to +35pts (scaled by confidence)

    Career overlap alone does NOT score relationship points.
    """
    score = 0
    reasons: list[str] = []

    # Connection distance
    if connection_distance == 1:
        score += 20
        reasons.append("Reachable via an explicitly recorded first-degree relationship.")
    elif connection_distance == 2:
        score += 10
        reasons.append("Reachable via an explicitly recorded second-degree path.")

    # Relationship strength
    strength_scores = {"strong": 15, "moderate": 8, "light": 3}
    score += strength_scores.get(relationship_strength.lower().strip(), 2)

    # Employer/company match
    if target_company:
        normalized_target = normalize_company_name(target_company)
        for employer in contact_employers:
            if normalize_company_name(employer) == normalized_target:
                score += 35
                reasons.append(
                    f"Career history includes {employer}; this is expertise context, "
                    "not proof of a personal relationship."
                )
                break
        else:
            # Partial sector match
            if target_sector:
                target_sector_key = target_sector.casefold()
                sector_matches = [ind for ind in contact_industries if target_sector_key in ind.casefold()]
                if sector_matches:
                    score += 18
                    reasons.append(f"Profile includes experience in '{target_sector}'.")

    return min(score, 100), reasons


def match_executive_to_contacts(
    executive_name: str,
    contact_candidates: list[EntityCandidate],
    *,
    minimum_fuzzy_confidence: float = 0.96,
) -> list[EntityCandidateMatch]:
    """
    Match an incoming executive name against network contacts.
    Returns matches sorted by confidence descending.
    Does NOT assert the person knows anybody; it only identifies possible
    name matches for human confirmation.
    """
    return match_contact_name(
        executive_name,
        contact_candidates,
        minimum_fuzzy_confidence=minimum_fuzzy_confidence,
    )
