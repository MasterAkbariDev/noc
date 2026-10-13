import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import structlog

from noc.llm.client import (
    LLMUnavailable,
    ProviderKeyRejected,
    ProviderRateLimited,
    ProviderUnavailable,
    QuotaExhausted,
)
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
    ) -> None:
        self._chains = chains
        self._fallback_enabled = fallback_enabled
        self._deadline = wait_deadline_seconds
        self._cooldowns = KeyCooldowns(clock)
        self._sleep = sleep

    def routes_for(self, tier: Tier) -> list[Route]:
        chain = self._chains.get(tier, [])
        if self._fallback_enabled or not chain:
            return chain
        primary = chain[0].provider.name
        return [route for route in chain if route.provider.name == primary]

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
        return await self._try(request, ready, primary=chain[0].provider.name)

    async def _try(self, request: LLMRequest, routes: list[Route], primary: str) -> LLMResponse:
        failures: list[str] = []
        for route in routes:
            try:
                wait_ms = await route.budget.acquire(self._deadline)
                response = await route.provider.complete(request, route.budget.model)
            except RECOVERABLE as exc:
                self._record_failure(route, exc)
                failures.append(f"{route.label}: {type(exc).__name__}")
                continue
            response.wait_ms = wait_ms
            response.fallback = route.provider.name != primary
            return response
        raise LLMUnavailable("; ".join(failures))

    def _record_failure(self, route: Route, error: Exception) -> None:
        cooldown = COOLDOWN_SECONDS.get(type(error))
        if cooldown is not None:
            self._cooldowns.cool(route.label, cooldown)
        logger.warning(
            "llm_route_failed",
            route=route.label,
            error=type(error).__name__,
            cooldown_seconds=cooldown,
        )
