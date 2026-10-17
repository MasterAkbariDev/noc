import openai
from openai import AsyncOpenAI

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.cassette import CassetteLLM
from noc.llm.client import LLMClient
from noc.llm.key_status import PostgresKeyStatus
from noc.llm.keys import KeyEntry, env_keys
from noc.llm.openai_compat import OpenAICompatProvider
from noc.llm.providers import ProviderConfig, load_providers, parse_chain_entry
from noc.llm.ratelimit import PostgresQuotaStore, RequestBudget
from noc.llm.recording import RecordingLLM
from noc.llm.redaction import RedactingLLM
from noc.llm.reloading import ReloadingLLM
from noc.llm.router import Route, RoutedLLM
from noc.llm.types import Tier
from noc.secret_store import SecretStore


def openai_client(
    config: ProviderConfig,
    api_key: str,
    timeout_seconds: float = 60.0,
    proxy: str | None = None,
) -> AsyncOpenAI:
    chosen = proxy if proxy is not None else config.proxy_url()
    http_client = openai.DefaultAsyncHttpxClient(proxy=chosen) if chosen else None
    return AsyncOpenAI(
        base_url=config.base_url,
        api_key=api_key,
        max_retries=0,
        timeout=timeout_seconds,
        http_client=http_client,
    )


def build_routed_llm(
    settings: Settings,
    sessions: SessionFactory,
    keys: list[KeyEntry] | None = None,
    proxies: dict[str, str | None] | None = None,
    chain_names: dict[Tier, list[str]] | None = None,
) -> RoutedLLM:
    document = load_providers(settings.llm_providers_file)
    entries = keys if keys is not None else env_keys(document)
    order = chain_names if chain_names is not None else document.chains
    quota_store = PostgresQuotaStore(sessions)
    chains: dict[Tier, list[Route]] = {}
    for tier, provider_names in order.items():
        routes: list[Route] = []
        for entry in (parse_chain_entry(name, tier) for name in provider_names):
            name = entry.provider
            config = document.providers[name]
            degraded = entry.model_tier != tier
            for key in (key for key in entries if key.provider == name):
                limits = config.limits_for(entry.model_tier, key.tier)
                if limits is None:
                    continue
                label = f"{key.label}/{entry.model_tier}" if degraded else key.label
                proxy = proxies.get(name) if proxies is not None else None
                client = openai_client(
                    config, key.secret, settings.llm_request_timeout_seconds, proxy
                )
                budget = RequestBudget(
                    label, limits.model, limits.rpm, limits.rpd, config.quota_timezone, quota_store
                )
                provider = OpenAICompatProvider(name, client, config.foreign_tool_call_extra)
                routes.append(Route(provider, budget, label, degraded))
        chains[tier] = routes
    return RoutedLLM(
        chains,
        settings.llm_fallback_enabled,
        settings.llm_wait_deadline_seconds,
        key_status=PostgresKeyStatus(sessions),
    )


def reloading_llm(settings: Settings, sessions: SessionFactory) -> ReloadingLLM:
    def build(
        keys: list[KeyEntry], proxies: dict[str, str | None], chains: dict[Tier, list[str]]
    ) -> LLMClient:
        return build_routed_llm(settings, sessions, keys, proxies, chains)

    return ReloadingLLM(settings, sessions, SecretStore(settings.secrets_dir), build)


def build_llm(settings: Settings, sessions: SessionFactory) -> LLMClient:
    cassette_path = settings.cassette_dir / f"{settings.cassette_name}.jsonl"
    core: LLMClient
    if settings.llm_mode == "replay":
        core = CassetteLLM(cassette_path, "replay")
    elif settings.llm_mode == "record":
        core = CassetteLLM(cassette_path, "record", reloading_llm(settings, sessions))
    else:
        core = reloading_llm(settings, sessions)
    return RecordingLLM(RedactingLLM(core), sessions)
