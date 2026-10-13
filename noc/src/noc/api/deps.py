import hmac
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from noc.auth.roles import Role, role_allows
from noc.auth.sessions import CSRF_HEADER, SESSION_COOKIE, load_session, sha256_hex
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuthSession

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
BEARER_CLIENT_NAME = "api-token"


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


def require_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.api_token
    if expected is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "NOC_API_TOKEN is not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


@dataclass(frozen=True)
class Principal:
    username: str
    role: Role
    user_id: uuid.UUID | None
    session_hash: str | None
    via: Literal["session", "token"]


def token_principal(settings: Settings, authorization: str) -> Principal:
    expected = settings.api_token
    supplied = authorization.removeprefix("Bearer ").strip()
    if expected is None or not hmac.compare_digest(
        supplied.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return Principal(
        username=BEARER_CLIENT_NAME,
        role=Role.ADMIN,
        user_id=None,
        session_hash=None,
        via="token",
    )


def check_csrf(auth_session: AuthSession, supplied: str | None) -> None:
    if supplied is None or not hmac.compare_digest(sha256_hex(supplied), auth_session.csrf_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token missing or invalid")


async def current_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> Principal:
    if authorization is not None:
        return token_principal(settings, authorization)
    if session_cookie is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    loaded = await load_session(session, session_cookie, settings, utc_now())
    await session.commit()
    if loaded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    auth_session, user = loaded
    if request.method not in SAFE_METHODS:
        check_csrf(auth_session, csrf_token)
    return Principal(
        username=user.username,
        role=Role(user.role),
        user_id=user.id,
        session_hash=auth_session.id_hash,
        via="session",
    )


def require_role(need: Role) -> Callable[[Principal], Principal]:
    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if not role_allows(principal.role, need):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "your role cannot do this")
        return principal

    return check
