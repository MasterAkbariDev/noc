import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

import httpx

from noc.llm.client import LLMError, ProviderKeyRejected, ProviderRateLimited
from noc.llm.key_status import KeyStatusSink, RecordedState
from noc.llm.keys import KeyEntry
from noc.llm.providers import ProviderConfig
from noc.llm.ratelimit import QuotaStore
from noc.llm.router import ModelProvider
from noc.llm.types import CallContext, ChatMessage, LLMRequest, Role

CHECK_AGENT: Final = "key-check"
CHECK_PROMPT: Final = "Reply with the single word OK."
DETAIL_MAX_LENGTH: Final = 300
PROXY_TIMEOUT_SECONDS: Final = 10.0

ProviderFactory = Callable[[ProviderConfig, KeyEntry], ModelProvider]


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    latency_ms: int
    model: str | None
    detail: str


def scrub(text: str, secret: str) -> str:
    return text.replace(secret, "***")[:DETAIL_MAX_LENGTH]


def failure_state(error: Exception) -> RecordedState | None:
    if isinstance(error, ProviderKeyRejected):
        return "rejected"
    if isinstance(error, ProviderRateLimited):
        return "cooling"
    return None


def check_request() -> LLMRequest:
    return LLMRequest(
        tier="small",
        messages=[ChatMessage(role=Role.USER, content=CHECK_PROMPT)],
        context=CallContext(agent=CHECK_AGENT),
    )


async def check_key(
    entry: KeyEntry,
    config: ProviderConfig,
    make_provider: ProviderFactory,
    quota: QuotaStore,
    status: KeyStatusSink,
) -> CheckResult:
    limits = config.limits_for("small", entry.tier)
    if limits is None:
        return CheckResult(False, 0, None, "the provider has no small model configured")
    day = datetime.now(ZoneInfo(config.quota_timezone)).date()
    if not await quota.reserve(entry.label, limits.model, day, limits.rpd):
        return CheckResult(False, 0, limits.model, "today's quota for this key is used up")
    started = time.monotonic()
    try:
        response = await make_provider(config, entry).complete(check_request(), limits.model)
    except (LLMError, TimeoutError) as error:
        elapsed = int((time.monotonic() - started) * 1000)
        state = failure_state(error)
        if state is not None:
            await status.record_failure(
                entry.label, entry.provider, state, None, type(error).__name__
            )
        detail = scrub(f"{type(error).__name__}: {error}", entry.secret)
        return CheckResult(False, elapsed, limits.model, detail)
    await status.record_success(entry.label, entry.provider)
    answer = (response.content or "").strip()[:40] or "(empty answer)"
    return CheckResult(True, response.latency_ms, response.model, f"answered: {answer}")


async def check_proxy(base_url: str, proxy: str) -> CheckResult:
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=PROXY_TIMEOUT_SECONDS) as http:
            response = await http.get(base_url)
    except httpx.HTTPError as error:
        elapsed = int((time.monotonic() - started) * 1000)
        return CheckResult(
            False, elapsed, None, f"{type(error).__name__}: {error}"[:DETAIL_MAX_LENGTH]
        )
    elapsed = int((time.monotonic() - started) * 1000)
    return CheckResult(True, elapsed, None, f"reached the provider, HTTP {response.status_code}")
