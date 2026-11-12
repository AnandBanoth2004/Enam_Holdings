from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finn_api.db.base import Base
from finn_api.db.demo_seed import DEMO_PORTFOLIO_ID, seed_demo_database
from finn_api.db.models import (
    Alert,
    AlertRule,
    AuditLog,
    Announcement,
    AnnouncementCategory,
    Company,
    CompanyAlias,
    DataSource,
    Document,
    DocumentChunk,
    DataSource,
    EntityMatch,
    FinancialMetric,
    FinancialStatementPeriod,
    GuidanceAssessment,
    ManagementGuidance,
    MarketDaily,
    NetworkEdge,
    NetworkPerson,
    NetworkRelationship,
    Organization,
    PersonEducation,
    PersonEmployment,
    Portfolio,
    PortfolioCompany,
    ResearchCitation,
    ResearchReport,
    ResearchRun,
    SourceSyncState,
    User,
    Workspace,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def _count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_complete_demo_seed_is_related_synthetic_and_idempotent(db_engine) -> None:
    with Session(db_engine, expire_on_commit=False) as session:
        initial = seed_demo_database(session, DATA)
        first_counts = {
            model: _count(session, model)
            for model in (
                Company,
                CompanyAlias,
                DataSource,
                Portfolio,
                PortfolioCompany,
                MarketDaily,
                Announcement,
                Document,
                DocumentChunk,
                EntityMatch,
                FinancialMetric,
                FinancialStatementPeriod,
                ManagementGuidance,
                GuidanceAssessment,
                ResearchRun,
                ResearchReport,
                ResearchCitation,
                Alert,
                AlertRule,
                NetworkPerson,
                Organization,
                PersonEmployment,
                PersonEducation,
                NetworkEdge,
                NetworkRelationship,
                AuditLog,
                AnnouncementCategory,
                SourceSyncState,
                User,
                Workspace,
            )
        }

        assert initial["portfolio_companies"] == 18
        assert first_counts[Company] == 22
        assert first_counts[CompanyAlias] == 22
        assert first_counts[PortfolioCompany] == 18
        assert first_counts[MarketDaily] == 110
        assert first_counts[EntityMatch] == 22
        assert first_counts[NetworkPerson] == 37
        assert first_counts[PersonEmployment] >= 36
        assert first_counts[PersonEducation] == 36
        assert first_counts[NetworkEdge] > 0
        assert first_counts[NetworkRelationship] > 0
        assert first_counts[Announcement] > 0
        assert first_counts[Document] == 7
        assert first_counts[DocumentChunk] == 7
        assert first_counts[ResearchCitation] == 4
        assert _count(session, FinancialStatementPeriod) == 4
        assert _count(session, FinancialMetric) == 16
        assert _count(session, ManagementGuidance) == 4
        assert _count(session, GuidanceAssessment) == 4
        assert _count(session, ResearchRun) == 4
        assert _count(session, ResearchReport) == 4
        assert _count(session, Alert) == 3
        assert _count(session, AnnouncementCategory) == 17
        assert set(session.scalars(select(Announcement.category)).all()) == {
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
        }
        assert _count(session, User) == 1
        assert _count(session, Workspace) == 1
        assert first_counts[AuditLog] == 1
        assert session.scalar(
            select(func.count()).select_from(Alert).where(Alert.announcement_id.is_not(None))
        ) == 2

        portfolio_company_ids = set(
            session.scalars(
                select(PortfolioCompany.company_id).where(
                    PortfolioCompany.portfolio_id == DEMO_PORTFOLIO_ID
                )
            ).all()
        )
        ad_hoc_symbols = {"POWERGRID", "M&M", "WIPRO", "CIPLA"}
        aliases = session.scalars(
            select(CompanyAlias).where(CompanyAlias.normalized_symbol.in_(ad_hoc_symbols))
        ).all()
        assert len(aliases) == 4
        assert all(alias.company_id not in portfolio_company_ids for alias in aliases)

        synthetic_fields = (
            (Announcement, "synthetic"),
            (PortfolioCompany, "synthetic"),
            (MarketDaily, "synthetic"),
            (Document, "synthetic"),
            (DocumentChunk, "synthetic"),
            (FinancialMetric, "is_synthetic"),
            (FinancialStatementPeriod, "is_synthetic"),
            (GuidanceAssessment, "is_synthetic"),
            (ManagementGuidance, "is_synthetic"),
            (NetworkPerson, "synthetic"),
            (NetworkEdge, "synthetic"),
            (NetworkRelationship, "is_synthetic"),
            (PersonEducation, "is_synthetic"),
            (PersonEmployment, "is_synthetic"),
            (ResearchCitation, "is_synthetic"),
            (ResearchReport, "is_synthetic"),
            (ResearchRun, "is_synthetic"),
            (EntityMatch, "is_synthetic"),
            (AuditLog, "is_synthetic"),
            (Alert, "is_synthetic"),
        )
        assert all(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(getattr(model, flag).is_(False))
            )
            == 0
            for model, flag in synthetic_fields
        )
        assert session.scalar(
            select(func.count()).select_from(DataSource).where(
                DataSource.source_key == "synthetic_demo",
                DataSource.is_synthetic.is_(True),
            )
        ) == 1

        seed_demo_database(session, DATA)
        assert {
            model: _count(session, model) for model in first_counts
        } == first_counts

        duplicate_alias = CompanyAlias(
            company_id=aliases[0].company_id,
            exchange=aliases[0].exchange,
            symbol=aliases[0].symbol,
            normalized_symbol=aliases[0].normalized_symbol,
        )
        session.add(duplicate_alias)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        entity_match = session.scalar(select(EntityMatch))
        session.add(
            EntityMatch(
                workspace_id=entity_match.workspace_id,
                source_id=entity_match.source_id,
                source_entity_key=entity_match.source_entity_key,
                candidate_key=entity_match.candidate_key,
                company_id=entity_match.company_id,
                confidence=entity_match.confidence,
                status=entity_match.status,
                rationale=entity_match.rationale,
                is_synthetic=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        relationship = session.scalar(select(NetworkRelationship))
        session.add(
            NetworkRelationship(
                workspace_id=relationship.workspace_id,
                from_person_id=relationship.from_person_id,
                to_person_id=relationship.to_person_id,
                relationship_type=relationship.relationship_type,
                strength=relationship.strength,
                evidence=relationship.evidence,
                source_id=relationship.source_id,
                is_synthetic=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
