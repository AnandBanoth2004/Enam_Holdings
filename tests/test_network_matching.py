"""
Tests for FINN entity matching and relevance scoring.

Validates:
- Exact name matching (must return confidence 1.0, method "exact")
- Fuzzy matching (must return method "fuzzy_proposed", confidence < 1.0)
- Single-token queries must be rejected
- Company suffix normalization (Ltd/Limited treated as equal)
- Career overlap does NOT assert acquaintance
- Relevance scoring rules
"""
from finn_api.network.matching import (
    EntityCandidate,
    match_company_name,
    match_contact_name,
    match_executive_to_contacts,
    normalize_company_name,
    normalize_entity_name,
    score_contact_relevance,
)


def test_normalize_entity_name_lowercases_and_strips():
    assert normalize_entity_name("  Tata  Consultancy  Services  ") == "tata consultancy services"
    assert normalize_entity_name("HDFC-Bank") == "hdfc bank"


def test_normalize_company_name_strips_suffixes():
    assert normalize_company_name("Tata Consultancy Services Limited") == "tata consultancy services"
    assert normalize_company_name("HDFC Bank Ltd") == "hdfc bank"
    assert normalize_company_name("Reliance Industries Ltd.") == "reliance industries"


def test_exact_contact_name_match():
    candidates = [
        EntityCandidate("1", "Mira Deshpande"),
        EntityCandidate("2", "Aarav Mehta"),
    ]
    matches = match_contact_name("Mira Deshpande", candidates)
    assert len(matches) == 1
    assert matches[0].candidate_id == "1"
    assert matches[0].confidence == 1.0
    assert matches[0].method == "exact"


def test_single_token_query_returns_no_matches():
    candidates = [EntityCandidate("1", "Mira Deshpande")]
    assert match_contact_name("Mira", candidates) == []


def test_fuzzy_contact_match_requires_high_confidence():
    candidates = [
        EntityCandidate("1", "Mira Deshpande"),
        EntityCandidate("2", "Mira Deshpandey"),
    ]
    # Close but not exact – should return fuzzy_proposed
    matches = match_contact_name("Mira Deshpand", candidates)
    assert all(m.method == "fuzzy_proposed" for m in matches)
    # Exact name should not appear as fuzzy
    exact_matches = match_contact_name("Mira Deshpande", candidates)
    assert exact_matches[0].method == "exact"


def test_company_name_exact_after_suffix_strip():
    candidates = [
        EntityCandidate("1", "Tata Consultancy Services Ltd."),
        EntityCandidate("2", "Tata Consumer Products Limited"),
    ]
    matches = match_company_name("Tata Consultancy Services Limited", candidates)
    assert len(matches) >= 1
    assert matches[0].candidate_id == "1"
    assert matches[0].method == "exact"


def test_company_match_rejects_weak_partial_names():
    # Single-word normalized query must return empty
    candidates = [EntityCandidate("1", "Reliance Industries Limited")]
    matches = match_company_name("Reliance", candidates)
    assert matches == []


def test_executive_match_delegates_to_contact_match():
    candidates = [
        EntityCandidate("a1", "Mira Deshpande"),
        EntityCandidate("a2", "Dev Malhotra"),
    ]
    results = match_executive_to_contacts("Mira Deshpande", candidates)
    assert results[0].candidate_id == "a1"
    assert results[0].confidence == 1.0


def test_score_contact_relevance_first_degree_strong():
    score, reasons = score_contact_relevance(
        contact_expertise=["Corporate Finance Director"],
        contact_industries=["Energy & Conglomerates"],
        contact_employers=["Reliance Industries Limited"],
        target_company="Reliance Industries Limited",
        connection_distance=1,
        relationship_strength="strong",
    )
    assert score >= 50  # 20 (1st degree) + 15 (strong) + 35 (employer match) = 70
    assert any("first-degree" in r for r in reasons)
    assert any("expertise context" in r for r in reasons)


def test_score_contact_relevance_career_overlap_does_not_add_relationship_points():
    """
    Career overlap should only be counted as expertise context, not as a
    relationship indicator. The relationship distance points come from
    explicit connection_distance.
    """
    # Second-degree contact with sector match but NO employer overlap
    score_2nd, reasons_2nd = score_contact_relevance(
        contact_expertise=["Financial Analyst"],
        contact_industries=["Financial Services"],
        contact_employers=["Morgan Stanley India"],
        target_company="HDFC Bank Limited",
        target_sector="Financial Services",
        connection_distance=2,
        relationship_strength="light",
    )
    # Should get: 10 (2nd degree) + 3 (light) + 18 (sector match) = 31
    assert 20 <= score_2nd <= 50
    assert any("second-degree" in r for r in reasons_2nd)


def test_score_contact_relevance_capped_at_100():
    score, _ = score_contact_relevance(
        contact_expertise=["CEO"],
        contact_industries=["Financial Services"],
        contact_employers=["HDFC Bank Limited"],
        target_company="HDFC Bank Limited",
        target_sector="Financial Services",
        connection_distance=1,
        relationship_strength="strong",
    )
    assert score <= 100
