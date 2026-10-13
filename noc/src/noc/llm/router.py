import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import structlog

from noc.db.base import utc_now
from noc.llm.client import (
    LLMUnavailable,
    ProviderBadGeneration,
    ProviderKeyRejected,
    ProviderRateLimited,
    ProviderUnavailable,
    QuotaExhausted,
)
from noc.llm.key_status import KeyStatusSink, NullKeyStatus, RecordedState
from noc.llm.ratelimit import RequestBudget
from noc.llm.types import LLMRequest, LLMResponse, Tier

logger = structlog.get_logger(__name__)

RECOVERABLE = (
    ProviderRateLimited,
    ProviderUnavailable,
    QuotaExhausted,
    ProviderKeyRejected,
    TimeoutError,
)
TRANSIENT = (ProviderUnavailable, TimeoutError)
OVERLOAD_BACKOFF_SECONDS = (5.0, 15.0)


def is_overload(error: Exception) -> bool:
    return isinstance(error, TRANSIENT) and not isinstance(error, ProviderBadGeneration)


COOLDOWN_SECONDS: dict[type[Exception], float] = {
    ProviderRateLimited: 60.0,
    QuotaExhausted: 600.0,
    ProviderKeyRejected: 3600.0,
}


class ModelProvider(Protocol):
    name: str

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...


@dataclass(frozen=True)
class Route:
    provider: ModelProvider
    budget: RequestBudget
    label: str
    degraded: bool = False


def recorded_state(error: Exception, cooldown: float | None) -> RecordedState:
    if isinstance(error, ProviderKeyRejected):
        return "rejected"
    return "ok" if cooldown is None else "cooling"


class KeyCooldowns:
    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._until: dict[str, float] = {}

    def cool(self, label: str, seconds: float) -> None:
        self._until[label] = max(self._until.get(label, 0.0), self._clock() + seconds)

    def remaining(self, label: str) -> float:
        return max(0.0, self._until.get(label, 0.0) - self._clock())

    def is_cooling(self, label: str) -> bool:
        return self.remaining(label) > 0


class RoutedLLM:
    def __init__(
        self,
        chains: dict[Tier, list[Route]],
        fallback_enabled: bool,
        wait_deadline_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        key_status: KeyStatusSink | None = None,
    ) -> None:
        self._chains = chains
        self._fallback_enabled = fallback_enabled
        self._deadline = wait_deadline_seconds
        self._cooldowns = KeyCooldowns(clock)
        self._sleep = sleep
        self._key_status: KeyStatusSink = key_status if key_status is not None else NullKeyStatus()

    def routes_for(self, tier: Tier) -> list[Route]:
        chain = self._chains.get(tier, [])
        if self._fallback_enabled or not chain:
            return chain
        primary = chain[0].provider.name
        return [route for route in chain if route.provider.name == primary and not route.degraded]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        chain = self.routes_for(request.tier)
        if not chain:
            raise LLMUnavailable(f"no route for tier {request.tier}")
        ready = [route for route in chain if not self._cooldowns.is_cooling(route.label)]
        if not ready:
            soonest = min(chain, key=lambda route: self._cooldowns.remaining(route.label))
            wait = self._cooldowns.remaining(soonest.label)
            if wait > self._deadline:
                raise LLMUnavailable(f"every key for tier {request.tier} is cooling down")
            await self._sleep(wait)
            ready = [soonest]
        primary = chain[0].provider.name
        waited = 0.0
        for backoff in (*OVERLOAD_BACKOFF_SECONDS, None):
            response, only_transient = await self._try(request, ready, primary)
            if response is not None:
                return response
            if backoff is None or not only_transient or waited + backoff > self._deadline:
                break
            await self._sleep(backoff)
            waited += backoff
            ready = [route for route in chain if not self._cooldowns.is_cooling(route.label)]
        raise LLMUnavailable(f"all routes failed for tier {request.tier}")

    async def _try(
        self, request: LLMRequest, routes: list[Route], primary: str
    ) -> tuple[LLMResponse | None, bool]:
        only_transient = bool(routes)
        overloaded: set[tuple[str, str]] = set()
        for route in routes:
            model = (route.provider.name, route.budget.model)
            if model in overloaded:
                continue
            try:
                wait_ms = await route.budget.acquire(self._deadline)
                response = await route.provider.complete(request, route.budget.model)
            except RECOVERABLE as exc:
                await self._record_failure(route, exc)
                only_transient = only_transient and isinstance(exc, TRANSIENT)
                if is_overload(exc):
                    overloaded.add(model)
                continue
            response.wait_ms = wait_ms
            response.fallback = route.provider.name != primary or route.degraded
            await self._notify_key_status(
                route.label, self._key_status.record_success(route.label, route.provider.name)
            )
            return response, only_transient
        return None, only_transient

    async def _record_failure(self, route: Route, error: Exception) -> None:
        cooldown = COOLDOWN_SECONDS.get(type(error))
        if cooldown is not None:
            self._cooldowns.cool(route.label, cooldown)
        logger.warning(
            "llm_route_failed",
            route=route.label,
            error=type(error).__name__,
            cooldown_seconds=cooldown,
        )
        cooling_until = None if cooldown is None else utc_now() + timedelta(seconds=cooldown)
        await self._notify_key_status(
            route.label,
            self._key_status.record_failure(
                route.label,
                route.provider.name,
                recorded_state(error, cooldown),
                cooling_until,
                type(error).__name__,
            ),
        )

    async def _notify_key_status(self, label: str, report: Awaitable[None]) -> None:
        try:
            await report
        except Exception as error:
            logger.warning("llm_key_status_failed", route=label, error=type(error).__name__)
