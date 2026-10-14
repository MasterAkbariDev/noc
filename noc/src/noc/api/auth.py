import asyncio
import hmac
import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, current_principal, get_session, get_settings_dep
from noc.api.schemas import (
    LoginRequest,
    MeView,
    PasswordChangeRequest,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupRequest,
    TotpSetupView,
)
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
from noc.auth.totp import matching_step, provisioning_uri
from noc.auth.users import (
    begin_totp_setup,
    claim_totp_step,
    clear_totp,
    enable_totp,
    find_user,
    subject_for,
)
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuthSession, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings_dep)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]

INVALID_LOGIN = "invalid username or password"
CURRENT_MISMATCH = "current password is wrong"
TOTP_REQUIRED = "authentication code required"
TOTP_INVALID = "invalid authentication code"
TOTP_ENROLMENT_REQUIRED = (
    "two-factor authentication is required for your role; ask an admin to enrol you"
)
TOTP_NOT_STARTED = "start the setup first"
TOTP_ALREADY_ON = "two-factor authentication is already on"
TOTP_REQUIRED_FOR_ROLE = "two-factor authentication cannot be turned off for your role"
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


def totp_required_for(user: User, settings: Settings) -> bool:
    return Role(user.role) in settings.totp_required_roles


def me_view(user: User, settings: Settings) -> MeView:
    return MeView(
        username=user.username,
        role=Role(user.role),
        via="session",
        totp_enabled=user.totp_enabled,
        totp_required=totp_required_for(user, settings),
    )


async def refuse_second_factor(
    session: AsyncSession, username: str, status_code: int, detail: str, reason: str
) -> HTTPException:
    await append_audit(
        session, ANONYMOUS_ACTOR, "login_failed", subject_for(username), {"reason": reason}
    )
    await session.commit()
    return HTTPException(status_code, detail)


async def check_second_factor(
    session: AsyncSession, user: User, code: str | None, attempt_id: int, settings: Settings
) -> None:
    if not user.totp_enabled:
        if totp_required_for(user, settings):
            raise await refuse_second_factor(
                session,
                user.username,
                status.HTTP_403_FORBIDDEN,
                TOTP_ENROLMENT_REQUIRED,
                "totp_not_enrolled",
            )
        return
    if not code:
        await drop_attempt(session, attempt_id)
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, TOTP_REQUIRED)
    step = matching_step(user.totp_secret or "", code, utc_now(), user.totp_last_step)
    if step is None or not await claim_totp_step(session, user.id, step):
        raise await refuse_second_factor(
            session, user.username, status.HTTP_401_UNAUTHORIZED, TOTP_INVALID, "totp"
        )


async def confirm_password(
    request: Request, session: AsyncSession, user: User, password: str, settings: Settings
) -> None:
    ip = client_ip(request)
    now = utc_now()
    attempt_id = await record_attempt(session, user.username, ip, now)
    if await over_limit(session, user.username, ip, now, settings.login_ip_limit):
        await drop_attempt(session, attempt_id)
        raise too_many_attempts()
    verified = await asyncio.to_thread(verify_password, user.password_hash, password)
    if not verified:
        await append_audit(session, user.username, "login_failed", subject_for(user.username), {})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, CURRENT_MISMATCH)
    await drop_attempt(session, attempt_id)


async def session_user(session: AsyncSession, principal: Principal) -> User:
    if principal.via != "session" or principal.user_id is None or principal.session_hash is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this needs a browser session")
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    return user


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
    if await over_limit(session, key, ip, now, settings.login_ip_limit):
        await drop_attempt(session, attempt_id)
        raise too_many_attempts()
    user = await find_login_user(session, key)
    checked_hash = user.password_hash if user is not None and not user.disabled else DUMMY_HASH
    verified = await asyncio.to_thread(verify_password, checked_hash, body.password)
    if user is None or user.disabled or not verified:
        await append_audit(session, ANONYMOUS_ACTOR, "login_failed", subject_for(key), {})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    await check_second_factor(session, user, body.totp, attempt_id, settings)
    await drop_attempt(session, attempt_id)
    if needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, body.password)
    await drop_presented_session(session, request)
    created = await create_session(session, user, ip, settings)
    user.last_login_at = now
    await append_audit(session, user.username, "login", subject_for(user.username), {})
    await session.commit()
    set_session_cookies(response, settings, created.token, created.csrf_token)
    return me_view(user, settings)


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
async def me(principal: CurrentPrincipal, settings: Config) -> MeView:
    return MeView(
        username=principal.username,
        role=principal.role,
        via=principal.via,
        totp_enabled=principal.totp_enabled,
        totp_required=principal.role in settings.totp_required_roles,
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    principal: CurrentPrincipal,
    session: Session,
    settings: Config,
) -> None:
    user = await session_user(session, principal)
    try:
        check_password_rules(body.new_password)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await confirm_password(request, session, user, body.current_password, settings)
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.password_changed_at = utc_now()
    await delete_user_sessions(session, user.id, keep_hash=principal.session_hash)
    await append_audit(session, user.username, "password_changed", subject_for(user.username), {})
    await session.commit()


@router.post("/totp/setup", response_model=TotpSetupView)
async def totp_setup(
    request: Request,
    body: TotpSetupRequest,
    principal: CurrentPrincipal,
    session: Session,
    settings: Config,
) -> TotpSetupView:
    user = await session_user(session, principal)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, TOTP_ALREADY_ON)
    await confirm_password(request, session, user, body.current_password, settings)
    secret = await begin_totp_setup(session, user)
    await session.commit()
    return TotpSetupView(
        secret=secret, uri=provisioning_uri(settings.totp_issuer, user.username, secret)
    )


@router.post("/totp/enable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_enable(
    body: TotpEnableRequest,
    principal: CurrentPrincipal,
    session: Session,
) -> None:
    user = await session_user(session, principal)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, TOTP_ALREADY_ON)
    if user.totp_secret is None:
        raise HTTPException(status.HTTP_409_CONFLICT, TOTP_NOT_STARTED)
    step = matching_step(user.totp_secret, body.code, utc_now(), user.totp_last_step)
    if step is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, TOTP_INVALID)
    await enable_totp(session, user, step, user.username)
    await delete_user_sessions(session, user.id, keep_hash=principal.session_hash)
    await session.commit()


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(
    request: Request,
    response: Response,
    body: TotpDisableRequest,
    principal: CurrentPrincipal,
    session: Session,
    settings: Config,
) -> None:
    user = await session_user(session, principal)
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, TOTP_NOT_STARTED)
    if totp_required_for(user, settings):
        raise HTTPException(status.HTTP_403_FORBIDDEN, TOTP_REQUIRED_FOR_ROLE)
    await confirm_password(request, session, user, body.current_password, settings)
    step = matching_step(user.totp_secret or "", body.code, utc_now(), user.totp_last_step)
    if step is None or not await claim_totp_step(session, user.id, step):
        raise await refuse_second_factor(
            session, user.username, status.HTTP_401_UNAUTHORIZED, TOTP_INVALID, "totp"
        )
    await clear_totp(session, user, user.username)
    await session.commit()
    clear_session_cookies(response, settings)
