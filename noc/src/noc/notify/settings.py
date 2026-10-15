import asyncio
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import NocSetting
from noc.llm.keys import KeyRefused, check_proxy, display_proxy
from noc.notify.telegram import TelegramUser, valid_token, valid_user_handle
from noc.secret_store import SecretStore

SETTING_KEY: Final = "telegram"
OFFSET_KEY: Final = "telegram-offset"
BOT_FILE_NAME: Final = "telegram-bot"
PROXY_FILE_NAME: Final = "telegram-proxy"
PANEL_URL_SCHEMES: Final = frozenset({"http", "https"})
MAX_ADMINS: Final = 20


class NotifyEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opened: bool = False
    approval: bool = True
    escalated: bool = True
    resolved: bool = True


class BotAdmin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str
    user_id: int | None = None
    username: str | None = None
    ready_since: datetime | None = None
    muted: bool = False
    added_by: str = ""


class TelegramSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paused: bool = False
    panel_url: str = ""
    events: NotifyEvents = Field(default_factory=NotifyEvents)
    admins: list[BotAdmin] = Field(default_factory=list)
    token_last4: str | None = None
    proxy_display: str | None = None
    active_since: datetime | None = None


class TelegramPanelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel_url: str = Field(default="", max_length=200)
    admins: list[str] = Field(default_factory=list, max_length=MAX_ADMINS)


def admin_for_handle(raw: str, actor: str) -> BotAdmin:
    handle = raw.strip()
    if not valid_user_handle(handle):
        raise KeyRefused(
            f"{handle or 'an empty entry'} is not a Telegram user id (digits) or @username"
        )
    if handle.startswith("@"):
        return BotAdmin(handle=handle.lower(), username=handle[1:].lower(), added_by=actor)
    return BotAdmin(handle=handle, user_id=int(handle), added_by=actor)


def find_admin(settings: TelegramSettings, user: TelegramUser) -> BotAdmin | None:
    username = (user.username or "").lower()
    for admin in settings.admins:
        if admin.user_id == user.id:
            return admin
        if admin.user_id is None and admin.username and admin.username == username:
            return admin
    return None


def find_by_handle(settings: TelegramSettings, handle: str) -> BotAdmin | None:
    wanted = handle.strip().lower()
    for admin in settings.admins:
        names = {admin.handle, f"@{admin.username}" if admin.username else ""}
        if admin.user_id is not None:
            names.add(str(admin.user_id))
        if wanted in names:
            return admin
    return None


def merge_admins(handles: list[str], current: list[BotAdmin], actor: str) -> list[BotAdmin]:
    current_settings = TelegramSettings(admins=current)
    merged: list[BotAdmin] = []
    for raw in handles:
        if not raw.strip():
            continue
        fresh = admin_for_handle(raw, actor)
        known = find_by_handle(current_settings, fresh.handle)
        candidate = known if known is not None else fresh
        if all(candidate.handle != existing.handle for existing in merged):
            merged.append(candidate)
    if len(merged) > MAX_ADMINS:
        raise KeyRefused(f"at most {MAX_ADMINS} admins")
    return merged


def recipients(settings: TelegramSettings) -> list[BotAdmin]:
    return [
        admin
        for admin in settings.admins
        if admin.user_id is not None and admin.ready_since is not None and not admin.muted
    ]


async def load_settings(session: AsyncSession) -> TelegramSettings:
    row = await session.get(NocSetting, SETTING_KEY)
    return TelegramSettings() if row is None else TelegramSettings.model_validate(row.value)


async def store_settings(
    session: AsyncSession, settings: TelegramSettings, actor: str, action: str
) -> None:
    row = await session.get(NocSetting, SETTING_KEY)
    value = settings.model_dump(mode="json")
    if row is None:
        session.add(NocSetting(key=SETTING_KEY, value=value, updated_by=actor))
    else:
        row.value = value
        row.updated_at = utc_now()
        row.updated_by = actor
    await session.flush()
    await append_audit(
        session,
        actor,
        action,
        "notify:telegram",
        settings.model_dump(mode="json", exclude={"active_since"}),
    )


async def load_offset(session: AsyncSession) -> int | None:
    row = await session.get(NocSetting, OFFSET_KEY)
    if row is None:
        return None
    offset = row.value.get("next")
    return offset if isinstance(offset, int) else None


async def store_offset(session: AsyncSession, offset: int) -> None:
    row = await session.get(NocSetting, OFFSET_KEY)
    if row is None:
        session.add(NocSetting(key=OFFSET_KEY, value={"next": offset}, updated_by="telegram"))
    else:
        row.value = {"next": offset}
        row.updated_at = utc_now()
    await session.flush()


def check_panel_url(raw: str) -> str:
    panel_url = raw.strip().rstrip("/")
    if panel_url:
        parts = urlsplit(panel_url)
        if parts.scheme not in PANEL_URL_SCHEMES or not parts.hostname:
            raise KeyRefused("the panel address must start with https:// or http://")
    return panel_url


async def update_settings(
    session: AsyncSession, update: TelegramPanelUpdate, actor: str
) -> TelegramSettings:
    current = await load_settings(session)
    settings = current.model_copy(
        update={
            "panel_url": check_panel_url(update.panel_url),
            "admins": merge_admins(update.admins, current.admins, actor),
        }
    )
    await store_settings(session, settings, actor, "telegram_settings_changed")
    return settings


async def set_token(
    session: AsyncSession, store: SecretStore, token: str | None, actor: str
) -> TelegramSettings:
    current = await load_settings(session)
    cleaned = token.strip() if token else None
    if cleaned:
        if not valid_token(cleaned):
            raise KeyRefused("this does not look like a bot token from @BotFather")
        await asyncio.to_thread(store.write, BOT_FILE_NAME, cleaned)
        settings = current.model_copy(
            update={"token_last4": cleaned[-4:], "active_since": utc_now()}
        )
        await store_settings(session, settings, actor, "telegram_token_set")
        return settings
    await asyncio.to_thread(store.delete, BOT_FILE_NAME)
    settings = current.model_copy(update={"token_last4": None})
    await store_settings(session, settings, actor, "telegram_token_removed")
    return settings


async def set_proxy(
    session: AsyncSession, store: SecretStore, url: str | None, actor: str
) -> TelegramSettings:
    current = await load_settings(session)
    cleaned = url.strip() if url else None
    if cleaned:
        check_proxy(cleaned)
        await asyncio.to_thread(store.write, PROXY_FILE_NAME, cleaned)
    else:
        await asyncio.to_thread(store.delete, PROXY_FILE_NAME)
    settings = current.model_copy(update={"proxy_display": display_proxy(cleaned)})
    await store_settings(session, settings, actor, "telegram_proxy_set")
    return settings


async def read_token(store: SecretStore) -> str | None:
    return await asyncio.to_thread(store.read, BOT_FILE_NAME)


async def read_proxy(store: SecretStore) -> str | None:
    return await asyncio.to_thread(store.read, PROXY_FILE_NAME)
