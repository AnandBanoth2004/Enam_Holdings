from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from finn_api.api.auth import get_current_user, require_workspace_membership
from finn_api.db.engine import get_db_session
from finn_api.db.models import User
from finn_api.network.service import (
    company_connections,
    contact_detail,
    contact_path,
    expertise_search,
    recommend_contacts,
    search_contacts,
)
from finn_api.schemas.network import (
    CompanyConnectionResponse,
    NetworkContactSearchResponse,
    NetworkContactResponse,
    NetworkPathResponse,
    NetworkRecommendationsResponse,
)

router = APIRouter(
    prefix="/network",
    tags=["network intelligence"],
    dependencies=[Depends(get_current_user)],
)


def _authorize(
    session: Session,
    *,
    workspace_id: UUID,
    user: User,
) -> None:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "network_resource_not_found",
            "message": "The requested network resource was not found in this workspace.",
        },
    )


@router.get("/contacts", response_model=NetworkContactSearchResponse)
def search_network_contacts(
    workspace_id: UUID,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkContactSearchResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    contacts = search_contacts(
        session,
        workspace_id=workspace_id,
        query=q,
        limit=limit,
    )
    return NetworkContactSearchResponse(total=len(contacts), contacts=contacts)


@router.get("/contacts/{contact_id}", response_model=NetworkContactResponse)
def get_network_contact(
    contact_id: UUID,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkContactResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    contact = contact_detail(session, workspace_id=workspace_id, person_id=contact_id)
    if contact is None:
        raise _not_found()
    return contact


@router.get("/expertise", response_model=NetworkContactSearchResponse)
def search_network_expertise(
    workspace_id: UUID,
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkContactSearchResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    contacts = expertise_search(
        session,
        workspace_id=workspace_id,
        query=q,
        limit=limit,
    )
    return NetworkContactSearchResponse(total=len(contacts), contacts=contacts)


@router.get("/companies/{ticker}/connections", response_model=CompanyConnectionResponse)
def get_company_network_connections(
    ticker: str,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> CompanyConnectionResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    result = company_connections(session, workspace_id=workspace_id, ticker=ticker)
    if result is None:
        raise _not_found()
    return result


@router.get("/second-degree", response_model=NetworkContactSearchResponse)
def get_second_degree_contacts(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkContactSearchResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    contacts = [
        contact
        for contact in search_contacts(
            session,
            workspace_id=workspace_id,
            query=None,
            limit=200,
        )
        if contact.connection_distance == 2
    ][:limit]
    return NetworkContactSearchResponse(total=len(contacts), contacts=contacts)


@router.get("/paths/{contact_id}", response_model=NetworkPathResponse)
def get_network_relationship_path(
    contact_id: UUID,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkPathResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    path = contact_path(session, workspace_id=workspace_id, person_id=contact_id)
    if path is None:
        raise _not_found()
    return path


@router.get("/recommendations", response_model=NetworkRecommendationsResponse)
def get_network_recommendations(
    workspace_id: UUID,
    workflow: Literal[
        "who_to_call",
        "second_degree_reach",
        "management_diligence",
        "sector_expertise",
        "keep_warm",
    ] = "who_to_call",
    ticker: str | None = None,
    executive: str | None = Query(default=None, max_length=160),
    expertise: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> NetworkRecommendationsResponse:
    _authorize(session, workspace_id=workspace_id, user=user)
    return recommend_contacts(
        session,
        workspace_id=workspace_id,
        workflow=workflow,
        ticker=ticker,
        executive=executive,
        expertise=expertise,
        limit=limit,
    )
