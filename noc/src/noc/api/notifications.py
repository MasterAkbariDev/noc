from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.auth.roles import Role
from noc.config import Settings
from noc.llm.keys import KeyRefused
from noc.notify.settings import (
    BotAdmin,
    NotifyEvents,
    TelegramPanelUpdate,
    TelegramSettings,
    load_settings,
    read_proxy,
    read_token,
    set_proxy,
    set_token,
    update_settings,
)
from noc.notify.telegram import TelegramError, TelegramSender
from noc.secret_store import SecretStore

TEST_MESSAGE = "[NOC] Test message: Telegram notifications from the NOC reach you here."
NOT_READY = "set a bot token and an admin, then have the admin send /start to the bot"

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]


def secret_store(settings: AppSettings) -> SecretStore:
    return SecretStore(settings.secrets_dir)


Store = Annotated[SecretStore, Depends(secret_store)]


class AdminView(BaseModel):
    handle: str
    username: str | None
    linked: bool
    muted: bool


class TelegramView(BaseModel):
    paused: bool
    panel_url: str
    events: NotifyEvents
    admins: list[AdminView]
    token_last4: str | None
    proxy_display: str | None


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(max_length=100)


class ProxyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=512)


class TestView(BaseModel):
    ok: bool
    detail: str


def admin_view(admin: BotAdmin) -> AdminView:
    return AdminView(
        handle=admin.handle,
        username=admin.username,
        linked=admin.ready_since is not None,
        muted=admin.muted,
    )


def view(settings: TelegramSettings) -> TelegramView:
    return TelegramView(
        paused=settings.paused,
        panel_url=settings.panel_url,
        events=settings.events,
        admins=[admin_view(admin) for admin in settings.admins],
        token_last4=settings.token_last4,
        proxy_display=settings.proxy_display,
    )


def refused(error: KeyRefused) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.get("/telegram")
async def get_telegram(admin: AdminPrincipal, session: Session) -> TelegramView:
    return view(await load_settings(session))


@router.put("/telegram")
async def put_telegram(
    body: TelegramPanelUpdate, admin: AdminPrincipal, session: Session
) -> TelegramView:
    try:
        settings = await update_settings(session, body, admin.username)
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return view(settings)


@router.put("/telegram/token")
async def put_token(
    body: TokenRequest, admin: AdminPrincipal, session: Session, store: Store
) -> TelegramView:
    try:
        settings = await set_token(session, store, body.token, admin.username)
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return view(settings)


@router.delete("/telegram/token")
async def delete_token(admin: AdminPrincipal, session: Session, store: Store) -> TelegramView:
    settings = await set_token(session, store, None, admin.username)
    await session.commit()
    return view(settings)


@router.put("/telegram/proxy")
async def put_proxy(
    body: ProxyRequest, admin: AdminPrincipal, session: Session, store: Store
) -> TelegramView:
    try:
        settings = await set_proxy(session, store, body.url, admin.username)
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return view(settings)


@router.post("/telegram/test")
async def test_telegram(admin: AdminPrincipal, session: Session, store: Store) -> TestView:
    settings = await load_settings(session)
    token = await read_token(store)
    linked = [item for item in settings.admins if item.user_id and item.ready_since]
    if not token or not linked:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_READY)
    sender = TelegramSender(token, await read_proxy(store))
    failures: list[str] = []
    for item in linked:
        try:
            await sender.send(str(item.user_id), TEST_MESSAGE)
        except TelegramError as error:
            failures.append(f"{item.handle}: {error}")
    if failures:
        return TestView(ok=False, detail="; ".join(failures))
    return TestView(ok=True, detail=f"sent to {len(linked)} admin(s)")
