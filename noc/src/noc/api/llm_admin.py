import asyncio
import uuid
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.api.schemas import (
    AddLlmKeyRequest,
    LlmChainEntryView,
    LlmChainOptionView,
    LlmChainView,
    LlmCheckRequest,
    LlmCheckView,
    LlmConfigView,
    LlmManagedKeyView,
    LlmModelLimitView,
    LlmProviderView,
    LlmProxyCheckView,
    LlmProxyView,
    SetChainRequest,
    SetProxyRequest,
)
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.models import LlmKey
from noc.db.session import SessionFactory
from noc.llm.chains import (
    ChainRefused,
    chain_options,
    chain_overrides,
    effective_chains,
    reset_chain,
    set_chain,
)
from noc.llm.factory import openai_client
from noc.llm.key_check import CheckResult, check_key, check_proxy
from noc.llm.key_status import PostgresKeyStatus
from noc.llm.keys import (
    KeyEntry,
    KeyRefused,
    ProxySetting,
    active_key_rows,
    add_key,
    all_keys,
    display_proxy,
    proxy_settings,
    reset_proxy_to_env,
    revoke_key,
    set_proxy,
)
from noc.llm.openai_compat import OpenAICompatProvider
from noc.llm.providers import ModelLimits, ProviderConfig, ProvidersDocument, load_providers
from noc.llm.ratelimit import PostgresQuotaStore
from noc.llm.router import ModelProvider
from noc.llm.types import Tier
from noc.secret_store import SecretStore

KEY_CHECK_TIMEOUT_SECONDS = 20.0
KEY_NOT_FOUND = "key not found"
PROVIDER_NOT_FOUND = "provider not found"
NO_PROXY = "this provider has no proxy configured"

router = APIRouter(prefix="/api/llm", tags=["llm"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]


def secret_store(settings: AppSettings) -> SecretStore:
    return SecretStore(settings.secrets_dir)


Store = Annotated[SecretStore, Depends(secret_store)]


def session_factory(request: Request) -> SessionFactory:
    factory: SessionFactory = request.app.state.sessions
    return factory


Sessions = Annotated[SessionFactory, Depends(session_factory)]


def limit_views(models: Mapping[Tier, ModelLimits]) -> list[LlmModelLimitView]:
    return [
        LlmModelLimitView(tier=tier, model=limits.model, rpm=limits.rpm, rpd=limits.rpd)
        for tier, limits in models.items()
    ]


def provider_view(name: str, config: ProviderConfig, proxy: ProxySetting) -> LlmProviderView:
    return LlmProviderView(
        name=name,
        base_url=config.base_url,
        proxy=LlmProxyView(display=display_proxy(proxy.url), source=proxy.source),
        free_models=limit_views(config.models),
        paid_models=limit_views(config.paid_models),
    )


def key_view(entry: KeyEntry, rows: dict[uuid.UUID, LlmKey]) -> LlmManagedKeyView:
    row = rows.get(entry.key_id) if entry.key_id is not None else None
    return LlmManagedKeyView(
        id=entry.key_id,
        label=entry.label,
        provider=entry.provider,
        name=entry.name,
        tier=entry.tier,
        source=entry.source,
        last4=entry.secret[-4:],
        created_at=row.created_at if row else None,
        created_by=row.created_by if row else None,
    )


def chain_views(
    document: ProvidersDocument, overrides: dict[Tier, list[str]]
) -> tuple[list[LlmChainView], list[LlmChainOptionView]]:
    options = {option.entry: option for option in chain_options(document)}
    views: list[LlmChainView] = []
    for tier, entries in effective_chains(document, overrides).items():
        rows = [
            LlmChainEntryView(
                entry=entry,
                provider=options[entry].provider,
                model_tier=options[entry].model_tier,
                model=options[entry].model,
                degraded=options[entry].model_tier != tier,
            )
            for entry in entries
        ]
        views.append(LlmChainView(tier=tier, entries=rows, customized=tier in overrides))
    choices = [
        LlmChainOptionView(
            entry=option.entry,
            provider=option.provider,
            model_tier=option.model_tier,
            model=option.model,
        )
        for option in options.values()
    ]
    return views, choices


async def config_view(
    session: AsyncSession, store: SecretStore, settings: Settings
) -> LlmConfigView:
    document = load_providers(settings.llm_providers_file)
    proxies = await proxy_settings(session, store, document)
    rows = {row.id: row for row in await active_key_rows(session)}
    keys = await all_keys(session, store, document)
    chains, choices = chain_views(document, await chain_overrides(session, document))
    return LlmConfigView(
        mode=settings.llm_mode,
        secrets_persistent=await asyncio.to_thread(store.is_persistent),
        providers=[
            provider_view(name, config, proxies[name])
            for name, config in document.providers.items()
        ],
        keys=[key_view(entry, rows) for entry in keys],
        chains=chains,
        chain_options=choices,
    )


def check_view(result: CheckResult) -> LlmCheckView:
    return LlmCheckView(
        ok=result.ok, latency_ms=result.latency_ms, model=result.model, detail=result.detail
    )


def provider_config(document: ProvidersDocument, name: str) -> ProviderConfig:
    config = document.providers.get(name)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PROVIDER_NOT_FOUND)
    return config


@router.get("/config")
async def get_config(
    admin: AdminPrincipal, session: Session, store: Store, settings: AppSettings
) -> LlmConfigView:
    return await config_view(session, store, settings)


@router.post("/keys")
async def create_key(
    body: AddLlmKeyRequest,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
    settings: AppSettings,
) -> LlmManagedKeyView:
    document = load_providers(settings.llm_providers_file)
    try:
        row = await add_key(
            session,
            store,
            document,
            body.provider,
            body.secret,
            body.tier,
            body.name,
            admin.username,
        )
    except KeyRefused as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    entry = KeyEntry(
        row.provider, body.secret.strip(), body.tier, "panel", key_id=row.id, name=row.name
    )
    return key_view(entry, {row.id: row})


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: uuid.UUID, admin: AdminPrincipal, session: Session, store: Store
) -> None:
    try:
        await revoke_key(session, store, key_id, admin.username)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, KEY_NOT_FOUND) from error
    await session.commit()


@router.post("/keys/check")
async def check_one_key(
    body: LlmCheckRequest,
    admin: AdminPrincipal,
    session: Session,
    sessions: Sessions,
    store: Store,
    settings: AppSettings,
) -> LlmCheckView:
    document = load_providers(settings.llm_providers_file)
    entries = {entry.label: entry for entry in await all_keys(session, store, document)}
    entry = entries.get(body.label)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, KEY_NOT_FOUND)
    proxies = await proxy_settings(session, store, document)
    proxy = proxies[entry.provider].url

    def make_provider(config: ProviderConfig, key: KeyEntry) -> ModelProvider:
        client = openai_client(config, key.secret, KEY_CHECK_TIMEOUT_SECONDS, proxy)
        return OpenAICompatProvider(key.provider, client, config.foreign_tool_call_extra)

    result = await check_key(
        entry,
        document.providers[entry.provider],
        make_provider,
        PostgresQuotaStore(sessions),
        PostgresKeyStatus(sessions),
    )
    return check_view(result)


@router.put("/providers/{name}/proxy")
async def put_proxy(
    name: str,
    body: SetProxyRequest,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
    settings: AppSettings,
) -> LlmConfigView:
    document = load_providers(settings.llm_providers_file)
    provider_config(document, name)
    try:
        await set_proxy(session, store, document, name, body.url, admin.username)
    except KeyRefused as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    return await config_view(session, store, settings)


@router.delete("/providers/{name}/proxy")
async def delete_proxy(
    name: str, admin: AdminPrincipal, session: Session, store: Store, settings: AppSettings
) -> LlmConfigView:
    document = load_providers(settings.llm_providers_file)
    provider_config(document, name)
    await reset_proxy_to_env(session, store, name, admin.username)
    await session.commit()
    return await config_view(session, store, settings)


@router.post("/providers/{name}/proxy/check")
async def check_provider_proxy(
    name: str, admin: AdminPrincipal, session: Session, store: Store, settings: AppSettings
) -> LlmCheckView:
    document = load_providers(settings.llm_providers_file)
    config = provider_config(document, name)
    proxy = (await proxy_settings(session, store, document))[name].url
    if proxy is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_PROXY)
    return check_view(await check_proxy(config.base_url, proxy))


@router.post("/proxies/check")
async def check_all_proxies(
    admin: AdminPrincipal, session: Session, store: Store, settings: AppSettings
) -> list[LlmProxyCheckView]:
    document = load_providers(settings.llm_providers_file)
    proxies = await proxy_settings(session, store, document)
    targets = [
        (name, config.base_url, url)
        for name, config in document.providers.items()
        if (url := proxies[name].url)
    ]
    results = await asyncio.gather(*(check_proxy(base_url, url) for _, base_url, url in targets))
    return [
        LlmProxyCheckView(
            provider=name,
            ok=result.ok,
            latency_ms=result.latency_ms,
            model=result.model,
            detail=result.detail,
        )
        for (name, _, _), result in zip(targets, results, strict=True)
    ]


@router.put("/chains/{tier}")
async def put_chain(
    tier: str,
    body: SetChainRequest,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
    settings: AppSettings,
) -> LlmConfigView:
    document = load_providers(settings.llm_providers_file)
    try:
        await set_chain(session, document, tier, body.entries, admin.username)
    except ChainRefused as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    return await config_view(session, store, settings)


@router.delete("/chains/{tier}")
async def delete_chain(
    tier: str, admin: AdminPrincipal, session: Session, store: Store, settings: AppSettings
) -> LlmConfigView:
    try:
        await reset_chain(session, tier, admin.username)
    except ChainRefused as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()
    return await config_view(session, store, settings)
