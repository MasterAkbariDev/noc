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
from noc.notify.telegram import valid_chat_id, valid_token
from noc.secret_store import SecretStore

SETTING_KEY: Final = "telegram"
BOT_FILE_NAME: Final = "telegram-bot"
PROXY_FILE_NAME: Final = "telegram-proxy"
PANEL_URL_SCHEMES: Final = frozenset({"http", "https"})


class NotifyEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opened: bool = False
    approval: bool = True
    escalated: bool = True
    resolved: bool = True


class TelegramSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    chat_id: str = ""
    panel_url: str = ""
    events: NotifyEvents = Field(default_factory=NotifyEvents)
    token_last4: str | None = None
    proxy_display: str | None = None
    enabled_at: datetime | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    chat_id: str = Field(default="", max_length=40)
    panel_url: str = Field(default="", max_length=200)
    events: NotifyEvents = Field(default_factory=NotifyEvents)


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
        settings.model_dump(mode="json", exclude={"enabled_at"}),
    )


def check_update(update: TelegramUpdate, current: TelegramSettings) -> None:
    chat_id = update.chat_id.strip()
    if chat_id and not valid_chat_id(chat_id):
        raise KeyRefused("the chat id is a number such as -1001234567890, or @channelname")
    if update.enabled and (not chat_id or current.token_last4 is None):
        raise KeyRefused("set a bot token and a chat id before turning notifications on")
    panel_url = update.panel_url.strip()
    if panel_url:
        parts = urlsplit(panel_url)
        if parts.scheme not in PANEL_URL_SCHEMES or not parts.hostname:
            raise KeyRefused("the panel address must start with https:// or http://")


async def update_settings(
    session: AsyncSession, update: TelegramUpdate, actor: str
) -> TelegramSettings:
    current = await load_settings(session)
    check_update(update, current)
    enabled_at = current.enabled_at
    if update.enabled and not current.enabled:
        enabled_at = utc_now()
    settings = current.model_copy(
        update={
            "enabled": update.enabled,
            "chat_id": update.chat_id.strip(),
            "panel_url": update.panel_url.strip().rstrip("/"),
            "events": update.events,
            "enabled_at": enabled_at,
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
        settings = current.model_copy(update={"token_last4": cleaned[-4:]})
        await store_settings(session, settings, actor, "telegram_token_set")
        return settings
    await asyncio.to_thread(store.delete, BOT_FILE_NAME)
    settings = current.model_copy(update={"token_last4": None, "enabled": False})
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
