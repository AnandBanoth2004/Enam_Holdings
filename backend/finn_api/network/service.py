from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from finn_api.db.models import (
    Announcement,
    Company,
    CompanyAlias,
    DataSource,
    EducationalInstitution,
    EntityMatch,
    NetworkPerson,
    NetworkRelationship,
    Organization,
    PersonEducation,
    PersonExperience,
    ResearchReport,
    Workspace,
)
from finn_api.network.matching import (
    EntityCandidate,
    EntityCandidateMatch,
    match_company_name,
    match_contact_name,
    normalize_company_name,
    normalize_entity_name,
)
from finn_api.schemas.network import (
    CompanyEntityMatchResponse,
    CompanyConnectionResponse,
    NetworkContactResponse,
    NetworkEducationResponse,
    NetworkExperienceResponse,
    NetworkPathStep,
    NetworkPathResponse,
    NetworkPathStep,
    NetworkRecommendationResponse,
    NetworkRecommendationsResponse,
)

Workflow = Literal[
    "who_to_call",
    "second_degree_reach",
    "management_diligence",
    "sector_expertise",
    "keep_warm",
]


@dataclass(frozen=True)
class RelationshipArc:
    source_id: UUID
    target_id: UUID
    relationship_type: str
    strength: str | None
    evidence: str | None
    last_interaction_at: datetime | None
    is_synthetic: bool


@dataclass(frozen=True)
class CandidatePath:
    distance: Literal[1, 2]
    steps: tuple[RelationshipArc, ...]


@dataclass(frozen=True)
class ExecutiveCandidate:
    name: str
    evidence: str


def investor_anchor_id(workspace_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"finn-network-investor:{workspace_id}")


def _relationship_arcs(session: Session, workspace_id: UUID) -> list[RelationshipArc]:
    source = aliased(NetworkPerson)
    target = aliased(NetworkPerson)
    rows = session.execute(
        select(NetworkRelationship, source.id, target.id)
        .join(source, source.id == NetworkRelationship.from_person_id)
        .join(target, target.id == NetworkRelationship.to_person_id)
        .where(
            NetworkRelationship.workspace_id == workspace_id,
            source.workspace_id == workspace_id,
            target.workspace_id == workspace_id,
        )
    ).all()
    return [
        RelationshipArc(
            source_id=relationship.from_person_id,
            target_id=relationship.to_person_id,
            relationship_type=relationship.relationship_type,
            strength=relationship.strength,
            evidence=relationship.evidence,
            last_interaction_at=relationship.last_interaction_at,
            is_synthetic=relationship.is_synthetic,
        )
        for relationship, _, _ in rows
    ]


def _find_path(
    arcs: list[RelationshipArc],
    *,
    start_id: UUID,
    target_id: UUID,
) -> CandidatePath | None:
    adjacency: dict[UUID, list[tuple[UUID, RelationshipArc]]] = defaultdict(list)
    for arc in arcs:
        adjacency[arc.source_id].append((arc.target_id, arc))
        adjacency[arc.target_id].append(
            (
                arc.source_id,
                RelationshipArc(
                    source_id=arc.target_id,
                    target_id=arc.source_id,
                    relationship_type=arc.relationship_type,
                    strength=arc.strength,
                    evidence=arc.evidence,
                    last_interaction_at=arc.last_interaction_at,
                    is_synthetic=arc.is_synthetic,
                ),
            )
        )
    queue = deque([(start_id, tuple())])
    visited = {start_id}
    while queue:
        current_id, path = queue.popleft()
        if current_id == target_id and path:
            if len(path) in (1, 2):
                return CandidatePath(len(path), path)  # type: ignore[arg-type]
            continue
        if len(path) >= 2:
            continue
        for next_id, arc in adjacency[current_id]:
            if next_id in visited:
                continue
            visited.add(next_id)
            queue.append((next_id, (*path, arc)))
    return None


def _experience_rows(session: Session, workspace_id: UUID, person_id: UUID):
    rows = session.execute(
        select(PersonExperience, Company.display_name, CompanyAlias.normalized_symbol)
        .outerjoin(Company, Company.id == PersonExperience.company_id)
        .outerjoin(
            CompanyAlias,
            (CompanyAlias.company_id == PersonExperience.company_id)
            & (CompanyAlias.exchange == "NSE"),
        )
        .where(
            PersonExperience.workspace_id == workspace_id,
            PersonExperience.person_id == person_id,
        )
        .order_by(PersonExperience.start_date.desc())
    ).all()
    return rows


def build_contact(
    session: Session,
    *,
    workspace_id: UUID,
    person: NetworkPerson,
    path: CandidatePath | None = None,
    anchor_name: str | None = None,
) -> NetworkContactResponse:
    experience_rows = _experience_rows(session, workspace_id, person.id)
    experiences = [
        NetworkExperienceResponse(
            organization=experience.organization,
            title=experience.title,
            sector=experience.sector,
            start_date=experience.start_date,
            end_date=experience.end_date,
            ticker=ticker,
            is_current=experience.end_date is None,
            is_synthetic=experience.synthetic,
        )
        for experience, _, ticker in experience_rows
    ]
    current_experience = next(
        (
            experience
            for experience, _, _ in experience_rows
            if experience.end_date is None
        ),
        None,
    )
    prior_employers = list(
        dict.fromkeys(
            experience.organization
            for experience, _, _ in experience_rows
            if experience.end_date is not None
        )
    )
    education_rows = session.execute(
        select(PersonEducation, EducationalInstitution.canonical_name)
        .join(
            EducationalInstitution,
            EducationalInstitution.id == PersonEducation.educational_institution_id,
        )
        .where(
            PersonEducation.workspace_id == workspace_id,
            PersonEducation.person_id == person.id,
        )
        .order_by(PersonEducation.end_date.desc())
    ).all()
    education = [
        NetworkEducationResponse(
            institution=institution,
            qualification=record.qualification,
            field_of_study=record.field_of_study,
            graduation_year=record.end_date.year if record.end_date else None,
            is_synthetic=record.is_synthetic,
        )
        for record, institution in education_rows
    ]
    latest_education = max(
        (item.graduation_year for item in education if item.graduation_year is not None),
        default=None,
    )
    sector_tags = list(
        dict.fromkeys(
            experience.sector
            for experience, _, _ in experience_rows
            if experience.sector
        )
    )
    expertise = list(
        dict.fromkeys(
            experience.title
            for experience, _, _ in experience_rows
            if experience.title
        )
    )
    companies = list(
        dict.fromkeys(
            company_name or experience.organization
            for experience, company_name, _ in experience_rows
        )
    )
    first_relationship = path.steps[0] if path else None
    next_person = (
        session.get(NetworkPerson, path.steps[0].target_id)
        if path and path.distance == 2
        else None
    )
    connection_type = (
        first_relationship.relationship_type
        if path and path.distance == 1
        else "via_contact"
        if path
        else None
    )
    evidence = (
        first_relationship.evidence
        if path and path.distance == 1
        else f"Explicitly recorded relationship path via {next_person.display_name}."
        if path and next_person
        else None
    )
    relationship_path = []
    if path:
        for arc in path.steps:
            path_person = session.get(NetworkPerson, arc.target_id)
            if path_person is None or path_person.workspace_id != workspace_id:
                continue
            relationship_path.append(
                NetworkPathStep(
                    contact_id=path_person.id,
                    name=path_person.display_name,
                    relationship_type=arc.relationship_type,
                    strength=arc.strength,
                    evidence=arc.evidence,
                    last_interaction=arc.last_interaction_at,
                )
            )
    return NetworkContactResponse(
        id=person.id,
        display_name=person.display_name,
        current_role=current_experience.title if current_experience else None,
        current_employer=current_experience.organization if current_experience else None,
        previous_employers=prior_employers,
        education=education,
        graduation_year=latest_education,
        expertise=expertise,
        industry_experience=sector_tags,
        companies_worked_with=companies,
        connection_type=connection_type,
        connection_distance=path.distance if path else None,
        last_interaction=first_relationship.last_interaction_at if first_relationship else None,
        relationship_strength=first_relationship.strength if first_relationship else None,
        relationship_evidence=evidence,
        relationship_path=relationship_path,
        is_synthetic=person.synthetic,
        experiences=experiences,
    )


def _path_response(
    session: Session,
    *,
    workspace_id: UUID,
    target: NetworkPerson,
    path: CandidatePath | None,
) -> NetworkPathResponse:
    if path is None:
        return NetworkPathResponse(
            contact_id=target.id,
            distance=None,
            path=[],
            explanation="No explicit relationship path is recorded; career overlap is not treated as a connection.",
        )
    steps = []
    for arc in path.steps:
        person = session.get(NetworkPerson, arc.target_id)
        if person is None or person.workspace_id != workspace_id:
            continue
        steps.append(
            NetworkPathStep(
                contact_id=person.id,
                name=person.display_name,
                relationship_type=arc.relationship_type,
                strength=arc.strength,
                evidence=arc.evidence,
                last_interaction=arc.last_interaction_at,
            )
        )
    if path.distance == 1:
        explanation = "Direct relationship recorded with explicit evidence."
    else:
        explanation = "Second-degree path is based only on the two explicit relationship records shown."
    return NetworkPathResponse(
        contact_id=target.id,
        distance=path.distance,
        path=steps,
        explanation=explanation,
    )


def search_contacts(
    session: Session,
    *,
    workspace_id: UUID,
    query: str | None,
    limit: int,
) -> list[NetworkContactResponse]:
    people = session.scalars(
        select(NetworkPerson)
        .where(
            NetworkPerson.workspace_id == workspace_id,
            NetworkPerson.source_type != "synthetic_investor_anchor",
        )
        .order_by(NetworkPerson.display_name)
    ).all()
    anchor_id = investor_anchor_id(workspace_id)
    arcs = _relationship_arcs(session, workspace_id)
    query_key = query.casefold().strip() if query else ""
    result = []
    for person in people:
        contact = build_contact(
            session,
            workspace_id=workspace_id,
            person=person,
            path=_find_path(arcs, start_id=anchor_id, target_id=person.id),
        )
        searchable = " ".join(
            [
                contact.display_name,
                contact.current_role or "",
                contact.current_employer or "",
                *contact.previous_employers,
                *contact.expertise,
                *contact.industry_experience,
                *contact.companies_worked_with,
            ]
        ).casefold()
        if query_key and query_key not in searchable:
            continue
        result.append(contact)
        if len(result) >= limit:
            break
    return result


def contact_detail(
    session: Session,
    *,
    workspace_id: UUID,
    person_id: UUID,
) -> NetworkContactResponse | None:
    person = session.scalar(
        select(NetworkPerson).where(
            NetworkPerson.id == person_id,
            NetworkPerson.workspace_id == workspace_id,
            NetworkPerson.source_type != "synthetic_investor_anchor",
        )
    )
    if person is None:
        return None
    path = _find_path(
        _relationship_arcs(session, workspace_id),
        start_id=investor_anchor_id(workspace_id),
        target_id=person.id,
    )
    return build_contact(
        session,
        workspace_id=workspace_id,
        person=person,
        path=path,
    )


def contact_path(
    session: Session,
    *,
    workspace_id: UUID,
    person_id: UUID,
) -> NetworkPathResponse | None:
    person = session.scalar(
        select(NetworkPerson).where(
            NetworkPerson.id == person_id,
            NetworkPerson.workspace_id == workspace_id,
            NetworkPerson.source_type != "synthetic_investor_anchor",
        )
    )
    if person is None:
        return None
    path = _find_path(
        _relationship_arcs(session, workspace_id),
        start_id=investor_anchor_id(workspace_id),
        target_id=person.id,
    )
    return _path_response(
        session,
        workspace_id=workspace_id,
        target=person,
        path=path,
    )


def company_connections(
    session: Session,
    *,
    workspace_id: UUID,
    ticker: str,
) -> CompanyConnectionResponse | None:
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == ticker.strip().upper().removesuffix(".NS"),
        )
    )
    if alias is None:
        return None
    company = session.get(Company, alias.company_id)
    if company is None:
        return None
    experience_rows = session.execute(
        select(PersonExperience, NetworkPerson)
        .join(NetworkPerson, NetworkPerson.id == PersonExperience.person_id)
        .where(
            NetworkPerson.workspace_id == workspace_id,
            PersonExperience.workspace_id == workspace_id,
            NetworkPerson.source_type != "synthetic_investor_anchor",
        )
    ).all()
    company_candidates = [
        EntityCandidate(str(company.id), company.legal_name),
        EntityCandidate(str(company.id), company.display_name),
    ]
    data_source = session.scalar(
        select(DataSource).where(DataSource.source_key == "network_entity_matching")
    )
    if data_source is None:
        data_source = DataSource(
            source_key="network_entity_matching",
            display_name="FINN network entity matching",
            source_type="internal",
            is_primary=False,
            is_synthetic=False,
        )
        session.add(data_source)
        session.flush()

    people_by_id: dict[UUID, NetworkPerson] = {}
    entity_matches: list[CompanyEntityMatchResponse] = []
    seen_experiences: set[UUID] = set()
    for experience, person in experience_rows:
        if experience.id in seen_experiences:
            continue
        seen_experiences.add(experience.id)
        if experience.company_id == company.id:
            confidence, method, status_key = 1.0, "company_id", "accepted"
        elif experience.company_id is None:
            matches = match_company_name(experience.organization, company_candidates)
            if not matches:
                continue
            match = matches[0]
            confidence = match.confidence
            method = match.method
            status_key = "accepted" if method == "exact" else "proposed"
        else:
            continue

        candidate_key = f"company:{company.id}"
        source_entity_key = f"person_experience:{experience.id}"
        rationale = (
            f"{method} company match: experience organization "
            f"'{experience.organization}' matched '{company.legal_name}' "
            f"with confidence {confidence:.4f}. This indicates company experience "
            "only and does not establish a personal relationship."
        )
        record = session.scalar(
            select(EntityMatch).where(
                EntityMatch.workspace_id == workspace_id,
                EntityMatch.source_id == data_source.id,
                EntityMatch.source_entity_key == source_entity_key,
                EntityMatch.candidate_key == candidate_key,
            )
        )
        if record is None:
            session.add(
                EntityMatch(
                    workspace_id=workspace_id,
                    source_id=data_source.id,
                    source_entity_key=source_entity_key,
                    candidate_key=candidate_key,
                    company_id=company.id,
                    confidence=Decimal(str(confidence)),
                    status=status_key,
                    rationale=rationale,
                    is_synthetic=experience.synthetic or person.synthetic,
                )
            )
        else:
            record.confidence = Decimal(str(confidence))
            record.status = status_key
            record.rationale = rationale
        people_by_id[person.id] = person
        entity_matches.append(
            CompanyEntityMatchResponse(
                contact_id=person.id,
                contact_name=person.display_name,
                confidence=confidence,
                status=status_key,
                method=method,
                evidence=rationale,
            )
        )

    people = sorted(people_by_id.values(), key=lambda item: item.display_name.casefold())
    arcs = _relationship_arcs(session, workspace_id)
    anchor_id = investor_anchor_id(workspace_id)
    contacts = [
        build_contact(
            session,
            workspace_id=workspace_id,
            person=person,
            path=_find_path(arcs, start_id=anchor_id, target_id=person.id),
        )
        for person in people
    ]
    if entity_matches:
        session.commit()
    return CompanyConnectionResponse(
        ticker=alias.normalized_symbol,
        company_name=company.display_name,
        contacts=contacts,
        match_confidence=1.0,
        match_evidence=[
            f"Exact NSE symbol match: {alias.normalized_symbol}.",
            f"{len(entity_matches)} profile experience record(s) matched this company; see individual match status and evidence.",
            "Employment relevance does not by itself establish a personal relationship.",
        ],
        entity_matches=entity_matches,
    )


def expertise_search(
    session: Session,
    *,
    workspace_id: UUID,
    query: str,
    limit: int,
) -> list[NetworkContactResponse]:
    return search_contacts(session, workspace_id=workspace_id, query=query, limit=limit)


def _persist_executive_matches(
    session: Session,
    *,
    workspace_id: UUID,
    workspace: Workspace,
    query: str,
    matches: list[EntityCandidateMatch],
    evidence: str,
) -> None:
    if not matches:
        return
    source = session.scalar(
        select(DataSource).where(DataSource.source_key == "network_entity_matching")
    )
    if source is None:
        source = DataSource(
            source_key="network_entity_matching",
            display_name="FINN network entity matching",
            source_type="internal",
            is_primary=False,
            is_synthetic=workspace.synthetic,
        )
        session.add(source)
        session.flush()
    entity_key = f"executive:{normalize_entity_name(query)}"[:240]
    for match in matches:
        candidate_id = UUID(match.candidate_id)
        candidate_key = f"network_person:{candidate_id}"
        record = session.scalar(
            select(EntityMatch).where(
                EntityMatch.workspace_id == workspace_id,
                EntityMatch.source_id == source.id,
                EntityMatch.source_entity_key == entity_key,
                EntityMatch.candidate_key == candidate_key,
            )
        )
        rationale = (
            f"{match.method} name match for '{query}' against '{match.display_name}' "
            f"(confidence {match.confidence:.4f}). Evidence: {evidence} "
            "Identity requires confirmation, and this match does not establish a personal relationship."
        )
        if record is None:
            session.add(
                EntityMatch(
                    workspace_id=workspace_id,
                    source_id=source.id,
                    source_entity_key=entity_key,
                    candidate_key=candidate_key,
                    person_id=candidate_id,
                    confidence=Decimal(str(match.confidence)),
                    status="proposed",
                    rationale=rationale,
                    is_synthetic=workspace.synthetic,
                )
            )
        else:
            record.confidence = Decimal(str(match.confidence))
            record.rationale = rationale
            record.status = "proposed"


def _executive_candidates_from_sources(
    session: Session,
    *,
    workspace_id: UUID,
    company_id: UUID,
    people: list[NetworkPerson],
) -> list[ExecutiveCandidate]:
    announcements = session.scalars(
        select(Announcement)
        .where(
            Announcement.company_id == company_id,
            Announcement.category == "management_change",
        )
        .order_by(Announcement.filed_at.desc())
        .limit(20)
    ).all()
    reports = session.scalars(
        select(ResearchReport)
        .where(
            ResearchReport.workspace_id == workspace_id,
            ResearchReport.company_id == company_id,
        )
        .order_by(ResearchReport.updated_at.desc())
        .limit(20)
    ).all()
    source_text = [
        (
            f"{announcement.headline} {announcement.body_text or ''}",
            f"announcement:{announcement.id} — {announcement.headline[:240]}",
        )
        for announcement in announcements
    ]

    def collect_strings(value: object, source_label: str) -> None:
        if isinstance(value, str):
            source_text.append((value, source_label))
        elif isinstance(value, dict):
            for item in value.values():
                collect_strings(item, source_label)
        elif isinstance(value, list):
            for item in value:
                collect_strings(item, source_label)

    for report in reports:
        collect_strings(
            report.content,
            f"research_report:{report.id} — {report.title}",
        )
        if report.summary:
            source_text.append(
                (report.summary, f"research_report:{report.id} — {report.title}")
            )
    candidates: dict[str, ExecutiveCandidate] = {}
    for text, evidence in source_text:
        content = normalize_entity_name(text)
        for person in people:
            name = normalize_entity_name(person.display_name)
            if name and f" {name} " in f" {content} ":
                candidates.setdefault(
                    person.display_name,
                    ExecutiveCandidate(
                        name=person.display_name,
                        evidence=evidence[:500],
                    ),
                )
    return list(candidates.values())


def recommend_contacts(
    session: Session,
    *,
    workspace_id: UUID,
    workflow: Workflow,
    ticker: str | None = None,
    executive: str | None = None,
    expertise: str | None = None,
    limit: int = 20,
) -> NetworkRecommendationsResponse:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        return NetworkRecommendationsResponse(
            workflow=workflow,
            ticker=ticker,
            executive=executive,
            recommendations=[],
            notice="The workspace does not exist.",
        )
    people = session.scalars(
        select(NetworkPerson)
        .where(
            NetworkPerson.workspace_id == workspace_id,
            NetworkPerson.source_type != "synthetic_investor_anchor",
        )
        .order_by(NetworkPerson.display_name)
    ).all()
    company: Company | None = None
    normalized_ticker = ticker.strip().upper().removesuffix(".NS") if ticker else None
    if normalized_ticker:
        alias = session.scalar(
            select(CompanyAlias).where(
                CompanyAlias.exchange == "NSE",
                CompanyAlias.normalized_symbol == normalized_ticker,
            )
        )
        if alias is not None:
            company = session.get(Company, alias.company_id)
    executive_candidates: list[ExecutiveCandidate] = []
    if executive:
        executive_candidates.append(
            ExecutiveCandidate(
                name=executive,
                evidence="Executive name supplied in an authenticated workspace request; confirm identity.",
            )
        )
    if workflow == "management_diligence" and not executive_candidates and company:
        executive_candidates.extend(
            _executive_candidates_from_sources(
                session,
                workspace_id=workspace_id,
                company_id=company.id,
                people=people,
            )
        )
    candidate_matches: list[EntityCandidateMatch] = []
    executive_evidence_by_contact: dict[UUID, str] = {}
    contact_candidates = [
        EntityCandidate(str(person.id), person.display_name)
        for person in people
    ]
    for candidate in executive_candidates:
        matches = match_contact_name(candidate.name, contact_candidates)
        candidate_matches.extend(matches)
        for match in matches:
            executive_evidence_by_contact[UUID(match.candidate_id)] = candidate.evidence
        _persist_executive_matches(
            session,
            workspace_id=workspace_id,
            workspace=workspace,
            query=candidate.name,
            matches=matches,
            evidence=candidate.evidence,
        )
    candidate_matches = list(
        {
            item.candidate_id: item
            for item in candidate_matches
        }.values()
    )
    anchor_id = investor_anchor_id(workspace_id)
    arcs = _relationship_arcs(session, workspace_id)
    query_key = (expertise or "").casefold().strip()
    executive_by_id = {UUID(item.candidate_id): item for item in candidate_matches}
    recommendations: list[NetworkRecommendationResponse] = []
    for person in people:
        path = _find_path(arcs, start_id=anchor_id, target_id=person.id)
        if path is None:
            continue
        if workflow == "second_degree_reach" and path.distance != 2:
            continue
        if workflow == "keep_warm" and path.distance != 1:
            continue
        contact = build_contact(
            session,
            workspace_id=workspace_id,
            person=person,
            path=path,
        )
        candidate_match = executive_by_id.get(person.id)
        if workflow == "management_diligence" and not candidate_match:
            continue

        reasons: list[str] = []
        score = 0
        if path.distance == 1:
            score += 20
            reasons.append("Reachable through an explicitly recorded first-degree relationship.")
        else:
            score += 10
            bridge_id = path.steps[0].target_id
            bridge = session.get(NetworkPerson, bridge_id)
            reasons.append(
                f"Second-degree route is explicitly recorded via {bridge.display_name if bridge else 'a contact'}."
            )
        strength = (path.steps[0].strength or "").casefold()
        strength_scores = {"strong": 15, "moderate": 8, "light": 3}
        score += strength_scores.get(strength, 2)
        if path.steps[0].evidence:
            reasons.append(f"Relationship evidence: {path.steps[0].evidence}")
        if path.steps[0].last_interaction_at:
            reasons.append(
                f"Last recorded interaction: {path.steps[0].last_interaction_at.date().isoformat()}."
            )

        experience_text = " ".join(
            [
                *contact.expertise,
                *contact.industry_experience,
                *contact.companies_worked_with,
            ]
        ).casefold()
        if company:
            company_experience = any(
                item.ticker == normalized_ticker
                or normalize_company_name(item.organization)
                == normalize_company_name(company.legal_name)
                for item in contact.experiences
            )
            if company_experience:
                score += 35
                reasons.append(
                    f"Experience history is linked to {company.display_name}; this is expertise evidence, not proof of a personal link."
                )
            elif company.sector and company.sector.casefold() in experience_text:
                score += 18
                reasons.append(f"Profile includes experience in {company.sector}.")
        if query_key:
            if query_key in experience_text:
                score += 25
                reasons.append(f"Profile experience matches the requested expertise '{expertise}'.")
            elif workflow == "sector_expertise":
                continue
        if candidate_match:
            score += round(35 * candidate_match.confidence)
            reasons.append(
                f"Executive name matched {contact.display_name} with {candidate_match.method} confidence {candidate_match.confidence:.2f}; confirm identity before relying on it."
            )
            reasons.append(
                f"Name-match source evidence: {executive_evidence_by_contact[person.id]}"
            )
        if workflow == "keep_warm" and path.steps[0].last_interaction_at:
            elapsed_days = (
                datetime.now(timezone.utc) - path.steps[0].last_interaction_at
            ).days
            if elapsed_days >= 180:
                score += 20
                reasons.append(f"Last explicit interaction was {elapsed_days} days ago.")
            else:
                score += 5
                reasons.append("The explicit relationship was active within the last 180 days.")
        if workflow == "who_to_call" and not (company or query_key):
            reasons.append("Ranked on explicit connection distance and recorded relationship strength.")
        recommendations.append(
            NetworkRecommendationResponse(
                contact=contact,
                score=min(score, 100),
                connection_distance=path.distance,
                reasons=reasons,
                path=_path_response(
                    session,
                    workspace_id=workspace_id,
                    target=person,
                    path=path,
                ).path,
                evidence_quality=(
                    "explicit_synthetic_fixture"
                    if all(arc.is_synthetic for arc in path.steps)
                    else "explicit_record"
                ),
                workflow=workflow,
            )
        )
    if candidate_matches:
        session.commit()
    recommendations.sort(
        key=lambda item: (-item.score, item.connection_distance, item.contact.display_name)
    )
    notice = (
        "Synthetic demonstration network: all identities and relationship evidence are fictional."
        if workspace.synthetic
        else "Recommendations use only explicitly recorded relationship evidence; shared career history is expertise context, not proof of acquaintance."
    )
    return NetworkRecommendationsResponse(
        workflow=workflow,
        ticker=normalized_ticker,
        executive=executive,
        recommendations=recommendations[:limit],
        notice=notice,
    )


def match_company_aliases(
    query: str,
    organizations: list[Organization],
) -> list[EntityCandidateMatch]:
    return match_company_name(
        query,
        [EntityCandidate(str(item.id), item.canonical_name) for item in organizations],
    )
