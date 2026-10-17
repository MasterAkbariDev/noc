import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import LlmKey, NocSetting
from noc.llm.providers import KeyTier, ProvidersDocument, key_label
from noc.secret_store import SecretStore

KeySource = Literal["env", "panel"]

KEY_PATTERN: Final = re.compile(r"^[A-Za-z0-9_\-.:]{8,256}$")
NAME_MAX_LENGTH: Final = 64
PROXY_SCHEMES: Final = frozenset({"http", "https"})
PROXY_SETTING_PREFIX: Final = "llm.proxy."
LLM_SETTING_PREFIX: Final = "llm."
TIER_ORDER: Final[dict[str, int]] = {"paid": 0, "free": 1}


class KeyRefused(ValueError):
    pass


@dataclass(frozen=True)
class KeyEntry:
    provider: str
    secret: str
    tier: KeyTier
    source: KeySource
    key_id: uuid.UUID | None = None
    name: str | None = None

    @property
    def label(self) -> str:
        return key_label(self.provider, self.secret)


@dataclass(frozen=True)
class ProxySetting:
    url: str | None
    source: Literal["env", "panel", "none"]


def key_secret_name(key_id: uuid.UUID) -> str:
    return f"llm-key-{key_id}"


def proxy_secret_name(provider: str) -> str:
    return f"llm-proxy-{provider}"


def proxy_setting_key(provider: str) -> str:
    return f"{PROXY_SETTING_PREFIX}{provider}"


def ordered(entries: list[KeyEntry]) -> list[KeyEntry]:
    return sorted(entries, key=lambda entry: TIER_ORDER[entry.tier])


def env_keys(document: ProvidersDocument) -> list[KeyEntry]:
    return [
        KeyEntry(provider=name, secret=secret, tier="free", source="env")
        for name, config in document.providers.items()
        for secret in config.api_keys()
    ]


async def active_key_rows(session: AsyncSession) -> list[LlmKey]:
    rows = await session.scalars(
        select(LlmKey).where(LlmKey.revoked_at.is_(None)).order_by(LlmKey.created_at)
    )
    return list(rows)


async def panel_keys(session: AsyncSession, store: SecretStore) -> list[KeyEntry]:
    entries: list[KeyEntry] = []
    for row in await active_key_rows(session):
        secret = await asyncio.to_thread(store.read, key_secret_name(row.id))
        if not secret:
            continue
        tier: KeyTier = "paid" if row.tier == "paid" else "free"
        entries.append(KeyEntry(row.provider, secret, tier, "panel", key_id=row.id, name=row.name))
    return entries


async def all_keys(
    session: AsyncSession, store: SecretStore, document: ProvidersDocument
) -> list[KeyEntry]:
    seen: set[str] = set()
    unique: list[KeyEntry] = []
    for entry in [*await panel_keys(session, store), *env_keys(document)]:
        if entry.label not in seen:
            seen.add(entry.label)
            unique.append(entry)
    return ordered(unique)


async def proxy_settings(
    session: AsyncSession, store: SecretStore, document: ProvidersDocument
) -> dict[str, ProxySetting]:
    configured = {
        row.key: row
        for row in await session.scalars(
            select(NocSetting).where(NocSetting.key.startswith(PROXY_SETTING_PREFIX))
        )
    }
    result: dict[str, ProxySetting] = {}
    for name, config in document.providers.items():
        if proxy_setting_key(name) in configured:
            url = await asyncio.to_thread(store.read, proxy_secret_name(name))
            result[name] = ProxySetting(url or None, "panel" if url else "none")
            continue
        env_url = config.proxy_url()
        result[name] = ProxySetting(env_url, "env" if env_url else "none")
    return result


async def config_version(session: AsyncSession) -> str:
    keys = await session.execute(select(func.count(), func.max(LlmKey.updated_at)))
    key_count, key_time = keys.one()
    proxies = await session.execute(
        select(func.count(), func.max(NocSetting.updated_at)).where(
            NocSetting.key.startswith(LLM_SETTING_PREFIX)
        )
    )
    proxy_count, proxy_time = proxies.one()
    return f"{key_count}|{key_time}|{proxy_count}|{proxy_time}"


def check_new_key(document: ProvidersDocument, provider: str, secret: str, name: str) -> None:
    if provider not in document.providers:
        raise KeyRefused(f"unknown provider {provider}")
    if KEY_PATTERN.fullmatch(secret) is None:
        raise KeyRefused("the key must be 8-256 characters without spaces")
    if not name.strip() or len(name) > NAME_MAX_LENGTH:
        raise KeyRefused(f"the name must be 1-{NAME_MAX_LENGTH} characters")


async def add_key(
    session: AsyncSession,
    store: SecretStore,
    document: ProvidersDocument,
    provider: str,
    secret: str,
    tier: KeyTier,
    name: str,
    actor: str,
) -> LlmKey:
    secret = secret.strip()
    check_new_key(document, provider, secret, name)
    label = key_label(provider, secret)
    existing = {entry.label for entry in await all_keys(session, store, document)}
    if label in existing:
        raise KeyRefused("this key is already configured")
    row = LlmKey(
        provider=provider,
        name=name.strip(),
        tier=tier,
        label=label,
        last4=secret[-4:],
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    await asyncio.to_thread(store.write, key_secret_name(row.id), secret)
    await append_audit(
        session,
        actor,
        "llm_key_added",
        f"llm:{label}",
        {"provider": provider, "tier": tier, "name": row.name},
    )
    return row


async def revoke_key(
    session: AsyncSession, store: SecretStore, key_id: uuid.UUID, actor: str
) -> LlmKey:
    row = await session.get(LlmKey, key_id)
    if row is None or row.revoked_at is not None:
        raise LookupError("key not found")
    now = utc_now()
    row.revoked_at = now
    row.revoked_by = actor
    row.updated_at = now
    await session.flush()
    await asyncio.to_thread(store.delete, key_secret_name(row.id))
    await append_audit(
        session, actor, "llm_key_revoked", f"llm:{row.label}", {"provider": row.provider}
    )
    return row


def check_proxy(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in PROXY_SCHEMES or not parts.hostname:
        raise KeyRefused("the proxy must be an http:// or https:// URL with a host")


def display_proxy(url: str | None) -> str | None:
    if url is None:
        return None
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    credentials = "***@" if parts.username or parts.password else ""
    return f"{parts.scheme}://{credentials}{parts.hostname}{port}"


async def set_proxy(
    session: AsyncSession,
    store: SecretStore,
    document: ProvidersDocument,
    provider: str,
    url: str | None,
    actor: str,
) -> None:
    if provider not in document.providers:
        raise KeyRefused(f"unknown provider {provider}")
    cleaned = url.strip() if url else None
    if cleaned:
        check_proxy(cleaned)
        await asyncio.to_thread(store.write, proxy_secret_name(provider), cleaned)
    else:
        await asyncio.to_thread(store.delete, proxy_secret_name(provider))
    setting = await session.get(NocSetting, proxy_setting_key(provider))
    value = {"display": display_proxy(cleaned)}
    if setting is None:
        session.add(NocSetting(key=proxy_setting_key(provider), value=value, updated_by=actor))
    else:
        setting.value = value
        setting.updated_at = utc_now()
        setting.updated_by = actor
    await session.flush()
    action = "llm_proxy_set" if cleaned else "llm_proxy_cleared"
    await append_audit(session, actor, action, f"llm:{provider}", {"proxy": display_proxy(cleaned)})


async def reset_proxy_to_env(
    session: AsyncSession, store: SecretStore, provider: str, actor: str
) -> None:
    setting = await session.get(NocSetting, proxy_setting_key(provider))
    if setting is not None:
        await session.delete(setting)
    await asyncio.to_thread(store.delete, proxy_secret_name(provider))
    await session.flush()
    await append_audit(session, actor, "llm_proxy_reset", f"llm:{provider}", {})
