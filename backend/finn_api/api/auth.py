from __future__ import annotations

from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.config import get_settings
from finn_api.db.engine import get_db_session
from finn_api.db.models import User, WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)
_ALLOWED_ALGORITHMS = ("ES256", "RS256", "EdDSA")


@lru_cache(maxsize=4)
def _jwk_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=5)


def _decode_subject(token: str) -> UUID:
    settings = get_settings()
    if not settings.auth_jwks_url or not settings.auth_issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "authentication_not_configured",
                "message": "Configure the authentication issuer and JWKS URL before using private APIs.",
            },
        )
    try:
        signing_key = _jwk_client(settings.auth_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["exp", "sub"]},
        )
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_access_token", "message": "A valid access token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "A bearer access token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = _decode_subject(credentials.credentials)
    user = session.scalar(select(User).where(User.auth_subject == subject))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unknown_user", "message": "The authenticated user is not provisioned."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_workspace_membership(
    session: Session,
    *,
    workspace_id: UUID,
    user: User,
) -> None:
    membership_id = session.scalar(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "workspace_access_denied",
                "message": "The authenticated user is not a member of this workspace.",
            },
        )
