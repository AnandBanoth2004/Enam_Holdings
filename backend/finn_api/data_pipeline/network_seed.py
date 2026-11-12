from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.db.models import (
    CompanyAlias,
    DataSource,
    EducationalInstitution,
    NetworkEdge,
    NetworkPerson,
    NetworkRelationship,
    Organization,
    PersonEducation,
    PersonEmployment,
    PersonExperience,
    Workspace,
)


class SyntheticDatasetError(ValueError):
    """Raised when a contact fixture is incomplete or not explicitly synthetic."""


@dataclass(frozen=True)
class SyntheticExperience:
    experience_type: str
    organization: str
    ticker: str | None
    sector: str
    title: str
    start_date: date
    end_date: date | None


@dataclass(frozen=True)
class SyntheticProfile:
    profile_id: str
    display_name: str
    sector: str
    experiences: tuple[SyntheticExperience, ...]


@dataclass(frozen=True)
class SyntheticRelationship:
    from_profile_id: str | None
    to_profile_id: str
    relationship_type: str
    strength: str
    last_interaction_at: date
    evidence: str


@dataclass(frozen=True)
class SyntheticContactDataset:
    dataset_id: str
    notice: str
    profiles: tuple[SyntheticProfile, ...]
    relationships: tuple[SyntheticRelationship, ...]


def load_synthetic_contact_dataset(path: Path) -> SyntheticContactDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("synthetic") is not True:
        raise SyntheticDatasetError("Contact dataset must be explicitly marked synthetic.")
    dataset_id = payload.get("dataset_id")
    notice = payload.get("notice")
    rows = payload.get("profiles")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise SyntheticDatasetError("Contact dataset must include a dataset_id.")
    if not isinstance(notice, str) or "fictional" not in notice.casefold():
        raise SyntheticDatasetError("Contact dataset must disclose that profiles are fictional.")
    if not isinstance(rows, list) or not 30 <= len(rows) <= 50:
        raise SyntheticDatasetError("Synthetic contact dataset must contain 30 to 50 profiles.")

    profile_ids: set[str] = set()
    display_names: set[str] = set()
    profiles: list[SyntheticProfile] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("synthetic") is not True:
            raise SyntheticDatasetError("Every profile must be explicitly marked synthetic.")
        profile_id = row.get("profile_id")
        name = row.get("display_name")
        experiences = row.get("experiences")
        sector = row.get("sector")
        if not all(isinstance(value, str) and value.strip() for value in (profile_id, name, sector)):
            raise SyntheticDatasetError("Each profile requires an ID, name, and sector.")
        if profile_id in profile_ids or name.casefold() in display_names:
            raise SyntheticDatasetError("Profile IDs and display names must be unique.")
        if not isinstance(experiences, list) or not experiences:
            raise SyntheticDatasetError(f"{profile_id} must have at least one experience.")
        profile_ids.add(profile_id)
        display_names.add(name.casefold())

        parsed_experiences: list[SyntheticExperience] = []
        for item in experiences:
            if not isinstance(item, dict):
                raise SyntheticDatasetError(f"{profile_id} experience must be an object.")
            organization = item.get("organization")
            item_sector = item.get("sector")
            title = item.get("title")
            kind = item.get("experience_type")
            start_year = item.get("start_year")
            end_year = item.get("end_year")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (organization, item_sector, title, kind)
            ):
                raise SyntheticDatasetError(f"{profile_id} experience fields are incomplete.")
            if not isinstance(start_year, int) or not 1900 <= start_year <= 2100:
                raise SyntheticDatasetError(f"{profile_id} has an invalid experience start year.")
            if end_year is not None and (
                not isinstance(end_year, int) or not start_year <= end_year <= 2100
            ):
                raise SyntheticDatasetError(f"{profile_id} has an invalid experience end year.")

            raw_ticker = item.get("ticker")
            ticker = normalize_nse_ticker(raw_ticker) if raw_ticker is not None else None
            parsed_experiences.append(
                SyntheticExperience(
                    experience_type=kind.strip(),
                    organization=organization.strip(),
                    ticker=ticker,
                    sector=item_sector.strip(),
                    title=title.strip(),
                    start_date=date(start_year, 1, 1),
                    end_date=date(end_year, 12, 31) if end_year is not None else None,
                )
            )
        profiles.append(
            SyntheticProfile(
                profile_id=profile_id.strip(),
                display_name=name.strip(),
                sector=sector.strip(),
                experiences=tuple(parsed_experiences),
            )
        )

    relationships: list[SyntheticRelationship] = []
    direct_connections = payload.get("direct_connections")
    explicit_relationships = payload.get("relationships")
    if not isinstance(direct_connections, list) or not direct_connections:
        raise SyntheticDatasetError("The fixture must define explicit investor relationships.")
    if not isinstance(explicit_relationships, list):
        raise SyntheticDatasetError("relationships must be a list of explicitly curated links.")

    def parse_relationship(
        row: object,
        *,
        from_profile_id: str | None,
    ) -> SyntheticRelationship:
        if not isinstance(row, dict):
            raise SyntheticDatasetError("Each network relationship must be an object.")
        to_profile_id = row.get("profile_id") if from_profile_id is None else row.get("to_profile_id")
        relationship_type = row.get("connection_type") if from_profile_id is None else row.get("relationship_type")
        strength = row.get("strength")
        evidence = row.get("evidence")
        if (
            not isinstance(to_profile_id, str)
            or to_profile_id not in profile_ids
            or not isinstance(relationship_type, str)
            or not relationship_type.strip()
            or not isinstance(strength, str)
            or not strength.strip()
            or not isinstance(evidence, str)
            or "fictional" not in evidence.casefold()
        ):
            raise SyntheticDatasetError("Relationships need valid contacts and explicit fictional evidence.")
        source_profile_id = (
            row.get("from_profile_id") if from_profile_id is not None else None
        )
        if from_profile_id is not None and (
            not isinstance(source_profile_id, str)
            or source_profile_id not in profile_ids
            or source_profile_id == to_profile_id
        ):
            raise SyntheticDatasetError("Relationship endpoints must be distinct known profiles.")
        try:
            last_interaction = date.fromisoformat(row["last_interaction"])
        except (KeyError, TypeError, ValueError) as error:
            raise SyntheticDatasetError("Relationships require an ISO last_interaction date.") from error
        return SyntheticRelationship(
            from_profile_id=source_profile_id,
            to_profile_id=to_profile_id,
            relationship_type=relationship_type.strip(),
            strength=strength.strip(),
            last_interaction_at=last_interaction,
            evidence=evidence.strip(),
        )

    relationships.extend(
        parse_relationship(row, from_profile_id=None) for row in direct_connections
    )
    relationships.extend(
        parse_relationship(
            row,
            from_profile_id=(
                row.get("from_profile_id") if isinstance(row, dict) else None
            ),
        )
        for row in explicit_relationships
    )
    if any(item.from_profile_id is None for item in relationships[len(direct_connections):]):
        raise SyntheticDatasetError("Contact-to-contact relationships require a from_profile_id.")

    return SyntheticContactDataset(
        dataset_id.strip(),
        notice.strip(),
        tuple(profiles),
        tuple(relationships),
    )


def seed_synthetic_contacts(
    session: Session,
    *,
    workspace_id: UUID,
    dataset: SyntheticContactDataset,
) -> int:
    """Idempotently seeds only marked synthetic profiles into the supplied workspace."""
    inserted = 0
    source_label = f"synthetic_fixture:{dataset.dataset_id}"
    data_source = session.scalar(
        select(DataSource).where(DataSource.source_key == "synthetic_network_fixture")
    )
    source_id = data_source.id if data_source is not None else None
    school_names = (
        "FINN Demo Institute of Management",
        "FINN Demo School of Technology",
        "FINN Demo School of Economics",
    )
    session.execute(
        delete(NetworkEdge).where(
            NetworkEdge.workspace_id == workspace_id,
            NetworkEdge.edge_type == "synthetic_peer",
        )
    )
    session.execute(
        delete(NetworkRelationship).where(
            NetworkRelationship.workspace_id == workspace_id,
            NetworkRelationship.relationship_type == "synthetic_peer",
        )
    )
    people_by_profile: dict[str, NetworkPerson] = {}
    for profile_index, profile in enumerate(dataset.profiles):
        person = session.scalar(
            select(NetworkPerson).where(
                NetworkPerson.workspace_id == workspace_id,
                NetworkPerson.display_name == profile.display_name,
                NetworkPerson.synthetic.is_(True),
                NetworkPerson.source_type == "synthetic_fixture",
            )
        )
        if person is None:
            person = NetworkPerson(
                workspace_id=workspace_id,
                display_name=profile.display_name,
                synthetic=True,
                source_type="synthetic_fixture",
                consent_status="synthetic",
                data_source_id=source_id,
            )
            session.add(person)
            session.flush()
            inserted += 1
        people_by_profile[profile.profile_id] = person

        for experience in profile.experiences:
            company_id = None
            organization = session.scalar(
                select(Organization).where(
                    Organization.canonical_name == experience.organization
                )
            )
            if experience.ticker:
                alias = session.scalar(
                    select(CompanyAlias).where(
                        CompanyAlias.exchange == "NSE",
                        CompanyAlias.normalized_symbol == experience.ticker,
                    )
                )
                company_id = alias.company_id if alias is not None else None
            if organization is None:
                organization = Organization(
                    canonical_name=experience.organization,
                    organization_type="employer",
                    company_id=company_id,
                    sector=experience.sector,
                    is_synthetic=company_id is None,
                    data_source_id=source_id,
                )
                session.add(organization)
                session.flush()
            existing = session.scalar(
                select(PersonExperience).where(
                    PersonExperience.workspace_id == workspace_id,
                    PersonExperience.person_id == person.id,
                    PersonExperience.experience_type == experience.experience_type,
                    PersonExperience.organization == experience.organization,
                    PersonExperience.title == experience.title,
                    PersonExperience.start_date == experience.start_date,
                    PersonExperience.end_date == experience.end_date,
                )
            )
            if existing is None:
                session.add(
                    PersonExperience(
                        workspace_id=workspace_id,
                        person_id=person.id,
                        experience_type=experience.experience_type,
                        organization=experience.organization,
                        company_id=company_id,
                        organization_id=organization.id,
                        sector=experience.sector,
                        title=experience.title,
                        start_date=experience.start_date,
                        end_date=experience.end_date,
                        source_label=source_label,
                        synthetic=True,
                        data_source_id=source_id,
                    )
                )
            employment = session.scalar(
                select(PersonEmployment).where(
                    PersonEmployment.workspace_id == workspace_id,
                    PersonEmployment.person_id == person.id,
                    PersonEmployment.organization_id == organization.id,
                    PersonEmployment.title == experience.title,
                    PersonEmployment.start_date == experience.start_date,
                )
            )
            if employment is None:
                session.add(
                    PersonEmployment(
                        workspace_id=workspace_id,
                        person_id=person.id,
                        organization_id=organization.id,
                        company_id=company_id,
                        title=experience.title,
                        start_date=experience.start_date,
                        end_date=experience.end_date,
                        source_label=source_label,
                        confidence=1,
                        is_synthetic=True,
                        source_id=source_id,
                    )
                )

        school_name = school_names[profile_index % len(school_names)]
        school = session.scalar(
            select(EducationalInstitution).where(
                EducationalInstitution.canonical_name == school_name
            )
        )
        if school is None:
            school = EducationalInstitution(
                canonical_name=school_name,
                institution_type="fictional_demo",
                is_synthetic=True,
                data_source_id=source_id,
            )
            session.add(school)
            session.flush()
        education_start = date(2004 + profile_index % 12, 1, 1)
        education_end = date(education_start.year + 3, 12, 31)
        education = session.scalar(
            select(PersonEducation).where(
                PersonEducation.workspace_id == workspace_id,
                PersonEducation.person_id == person.id,
                PersonEducation.educational_institution_id == school.id,
            )
        )
        if education is None:
            session.add(
                PersonEducation(
                    workspace_id=workspace_id,
                    person_id=person.id,
                    educational_institution_id=school.id,
                    qualification="Bachelor of Business Administration",
                    field_of_study=profile.sector,
                    start_date=education_start,
                    end_date=education_end,
                    source_label=source_label,
                    confidence=1,
                    is_synthetic=True,
                    source_id=source_id,
                )
            )

    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise SyntheticDatasetError("The target workspace does not exist.")
    anchor_id = uuid5(NAMESPACE_URL, f"finn-network-investor:{workspace_id}")
    anchor = session.get(NetworkPerson, anchor_id)
    if anchor is None:
        anchor = NetworkPerson(
            id=anchor_id,
            workspace_id=workspace_id,
            display_name="FINN Workspace Investor",
            synthetic=True,
            source_type="synthetic_investor_anchor",
            consent_status="synthetic",
            data_source_id=source_id,
        )
        session.add(anchor)
        session.flush()

    for relationship in dataset.relationships:
        from_person = (
            anchor
            if relationship.from_profile_id is None
            else people_by_profile[relationship.from_profile_id]
        )
        to_person = people_by_profile[relationship.to_profile_id]
        interaction_at = datetime.combine(
            relationship.last_interaction_at,
            time.min,
            tzinfo=timezone.utc,
        )
        record = session.scalar(
            select(NetworkRelationship).where(
                NetworkRelationship.workspace_id == workspace_id,
                NetworkRelationship.from_person_id == from_person.id,
                NetworkRelationship.to_person_id == to_person.id,
                NetworkRelationship.relationship_type == relationship.relationship_type,
            )
        )
        if record is None:
            session.add(
                NetworkRelationship(
                    workspace_id=workspace_id,
                    from_person_id=from_person.id,
                    to_person_id=to_person.id,
                    relationship_type=relationship.relationship_type,
                    strength=relationship.strength,
                    evidence=relationship.evidence,
                    last_interaction_at=interaction_at,
                    source_id=source_id,
                    is_synthetic=True,
                )
            )
        edge = session.scalar(
            select(NetworkEdge).where(
                NetworkEdge.workspace_id == workspace_id,
                NetworkEdge.from_person_id == from_person.id,
                NetworkEdge.to_person_id == to_person.id,
                NetworkEdge.edge_type == relationship.relationship_type,
            )
        )
        if edge is None:
            session.add(
                NetworkEdge(
                    workspace_id=workspace_id,
                    from_person_id=from_person.id,
                    to_person_id=to_person.id,
                    edge_type=relationship.relationship_type,
                    relationship_strength=relationship.strength,
                    evidence=relationship.evidence,
                    source_label=source_label,
                    data_source_id=source_id,
                    verified_by_user=False,
                    synthetic=True,
                )
            )
    session.commit()
    return inserted
