import openai
from openai import AsyncOpenAI

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.cassette import CassetteLLM
from noc.llm.client import LLMClient
from noc.llm.key_status import PostgresKeyStatus
from noc.llm.openai_compat import OpenAICompatProvider
from noc.llm.providers import ProviderConfig, key_label, load_providers, parse_chain_entry
from noc.llm.ratelimit import PostgresQuotaStore, RequestBudget
from noc.llm.recording import RecordingLLM
from noc.llm.redaction import RedactingLLM
from noc.llm.router import Route, RoutedLLM
from noc.llm.types import Tier


def openai_client(
    config: ProviderConfig, api_key: str, timeout_seconds: float = 60.0
) -> AsyncOpenAI:
    proxy = config.proxy_url()
    http_client = openai.DefaultAsyncHttpxClient(proxy=proxy) if proxy else None
    return AsyncOpenAI(
        base_url=config.base_url,
        api_key=api_key,
        max_retries=0,
        timeout=timeout_seconds,
        http_client=http_client,
    )


def build_routed_llm(settings: Settings, sessions: SessionFactory) -> RoutedLLM:
    document = load_providers(settings.llm_providers_file)
    quota_store = PostgresQuotaStore(sessions)
    chains: dict[Tier, list[Route]] = {}
    for tier, provider_names in document.chains.items():
        routes: list[Route] = []
        for entry in (parse_chain_entry(name, tier) for name in provider_names):
            name = entry.provider
            config = document.providers[name]
            if entry.model_tier not in config.models:
                continue
            limits = config.models[entry.model_tier]
            degraded = entry.model_tier != tier
            for api_key in config.api_keys():
                label = key_label(name, api_key)
                if degraded:
                    label = f"{label}/{entry.model_tier}"
                client = openai_client(config, api_key, settings.llm_request_timeout_seconds)
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


def build_llm(settings: Settings, sessions: SessionFactory) -> LLMClient:
    cassette_path = settings.cassette_dir / f"{settings.cassette_name}.jsonl"
    core: LLMClient
    if settings.llm_mode == "replay":
        core = CassetteLLM(cassette_path, "replay")
    elif settings.llm_mode == "record":
        core = CassetteLLM(cassette_path, "record", build_routed_llm(settings, sessions))
    else:
        core = build_routed_llm(settings, sessions)
    return RecordingLLM(RedactingLLM(core), sessions)
