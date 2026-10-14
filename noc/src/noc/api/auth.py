import asyncio
import hmac
import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, current_principal, get_session, get_settings_dep
from noc.api.schemas import LoginRequest, MeView, PasswordChangeRequest
from noc.audit.chain import append_audit
from noc.auth.login_limits import (
    USERNAME_MAX_LENGTH,
    WINDOW,
    drop_attempt,
    over_limit,
    record_attempt,
)
from noc.auth.passwords import (
    DUMMY_HASH,
    check_password_rules,
    hash_password,
    needs_rehash,
    verify_password,
)
from noc.auth.roles import Role
from noc.auth.sessions import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    delete_session,
    delete_user_sessions,
    sha256_hex,
)
from noc.auth.users import find_user, subject_for
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuthSession, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings_dep)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]

INVALID_LOGIN = "invalid username or password"
CURRENT_MISMATCH = "current password is wrong"
TOO_MANY_ATTEMPTS = "too many attempts, try again later"
JSON_MEDIA_TYPE = "application/json"
IP_MAX_LENGTH = 64
UNKNOWN_CLIENT = "unknown"
CSRF_FAILED = "csrf token missing or invalid"
ANONYMOUS_ACTOR = "anonymous"
SECONDS_PER_HOUR = 3600


def client_ip(request: Request) -> str:
    host = request.client.host if request.client is not None else ""
    try:
        return str(ipaddress.ip_address(host))[:IP_MAX_LENGTH]
    except ValueError:
        return UNKNOWN_CLIENT


def login_key(username: str) -> str:
    return username.strip().lower()[:USERNAME_MAX_LENGTH]


def set_session_cookies(
    response: Response, settings: Settings, token: str, csrf_token: str
) -> None:
    max_age = settings.session_absolute_hours * SECONDS_PER_HOUR
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="strict",
    )


def too_many_attempts() -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        TOO_MANY_ATTEMPTS,
        headers={"Retry-After": str(int(WINDOW.total_seconds()))},
    )


async def read_login(request: Request) -> LoginRequest:
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != JSON_MEDIA_TYPE:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "login expects a JSON body")
    try:
        return LoginRequest.model_validate_json(await request.body())
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "username and password are required"
        ) from error


async def find_login_user(session: AsyncSession, key: str) -> User | None:
    try:
        return await find_user(session, key)
    except ValueError:
        return None


async def drop_presented_session(session: AsyncSession, request: Request) -> None:
    presented = request.cookies.get(SESSION_COOKIE)
    if presented is not None:
        await delete_session(session, sha256_hex(presented))


async def end_session(session: AsyncSession, row: AuthSession) -> None:
    user = await session.get(User, row.user_id)
    await delete_session(session, row.id_hash)
    if user is not None:
        await append_audit(session, user.username, "logout", subject_for(user.username), {})
    await session.commit()


def csrf_matches(row: AuthSession, supplied: str | None) -> bool:
    return supplied is not None and hmac.compare_digest(sha256_hex(supplied), row.csrf_hash)


@router.post("/login", response_model=MeView)
async def login(
    request: Request,
    response: Response,
    session: Session,
    settings: Config,
) -> MeView:
    body = await read_login(request)
    key = login_key(body.username)
    ip = client_ip(request)
    now = utc_now()
    attempt_id = await record_attempt(session, key, ip, now)
    if await over_limit(session, key, ip, now):
        await drop_attempt(session, attempt_id)
        raise too_many_attempts()
    user = await find_login_user(session, key)
    checked_hash = user.password_hash if user is not None and not user.disabled else DUMMY_HASH
    verified = await asyncio.to_thread(verify_password, checked_hash, body.password)
    if user is None or user.disabled or not verified:
        await append_audit(session, ANONYMOUS_ACTOR, "login_failed", subject_for(key), {})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    await drop_attempt(session, attempt_id)
    if needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, body.password)
    await drop_presented_session(session, request)
    created = await create_session(session, user, ip, settings)
    user.last_login_at = now
    await append_audit(session, user.username, "login", subject_for(user.username), {})
    await session.commit()
    set_session_cookies(response, settings, created.token, created.csrf_token)
    return MeView(username=user.username, role=Role(user.role), via="session")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Session,
    settings: Config,
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> None:
    presented = request.cookies.get(SESSION_COOKIE)
    row = await session.get(AuthSession, sha256_hex(presented)) if presented is not None else None
    if row is not None:
        if not csrf_matches(row, csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, CSRF_FAILED)
        await end_session(session, row)
    clear_session_cookies(response, settings)


@router.get("/me", response_model=MeView)
async def me(principal: CurrentPrincipal) -> MeView:
    return MeView(username=principal.username, role=principal.role, via=principal.via)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    principal: CurrentPrincipal,
    session: Session,
) -> None:
    if principal.via != "session" or principal.user_id is None or principal.session_hash is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "password change needs a browser session")
    try:
        check_password_rules(body.new_password)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    ip = client_ip(request)
    now = utc_now()
    attempt_id = await record_attempt(session, user.username, ip, now)
    if await over_limit(session, user.username, ip, now):
        await drop_attempt(session, attempt_id)
        raise too_many_attempts()
    verified = await asyncio.to_thread(verify_password, user.password_hash, body.current_password)
    if not verified:
        await append_audit(session, user.username, "login_failed", subject_for(user.username), {})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, CURRENT_MISMATCH)
    await drop_attempt(session, attempt_id)
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.password_changed_at = now
    await delete_user_sessions(session, user.id, keep_hash=principal.session_hash)
    await append_audit(session, user.username, "password_changed", subject_for(user.username), {})
    await session.commit()
