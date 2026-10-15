from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.auth.roles import Role
from noc.config import Settings
from noc.llm.keys import KeyRefused
from noc.notify.settings import (
    NotifyEvents,
    TelegramSettings,
    TelegramUpdate,
    load_settings,
    read_proxy,
    read_token,
    set_proxy,
    set_token,
    update_settings,
)
from noc.notify.telegram import TelegramError, TelegramSender
from noc.secret_store import SecretStore

TEST_MESSAGE = "[NOC] Test message: Telegram notifications from the NOC reach this chat."
NOT_READY = "set a bot token and a chat id first"

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]


def secret_store(settings: AppSettings) -> SecretStore:
    return SecretStore(settings.secrets_dir)


Store = Annotated[SecretStore, Depends(secret_store)]


class TelegramView(BaseModel):
    enabled: bool
    chat_id: str
    panel_url: str
    events: NotifyEvents
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


def view(settings: TelegramSettings) -> TelegramView:
    return TelegramView.model_validate(settings.model_dump(exclude={"enabled_at"}))


def refused(error: KeyRefused) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.get("/telegram")
async def get_telegram(admin: AdminPrincipal, session: Session) -> TelegramView:
    return view(await load_settings(session))


@router.put("/telegram")
async def put_telegram(
    body: TelegramUpdate, admin: AdminPrincipal, session: Session
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
    if not token or not settings.chat_id:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_READY)
    try:
        await TelegramSender(token, await read_proxy(store)).send(settings.chat_id, TEST_MESSAGE)
    except TelegramError as error:
        return TestView(ok=False, detail=str(error))
    return TestView(ok=True, detail="sent; check the chat")
