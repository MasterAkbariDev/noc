from dataclasses import dataclass
from typing import Protocol

import structlog

from noc.llm.client import LLMUnavailable, ProviderRateLimited, ProviderUnavailable, QuotaExhausted
from noc.llm.ratelimit import RequestBudget
from noc.llm.types import LLMRequest, LLMResponse, Tier

logger = structlog.get_logger(__name__)

RECOVERABLE = (ProviderRateLimited, ProviderUnavailable, QuotaExhausted, TimeoutError)


class ModelProvider(Protocol):
    name: str

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...


@dataclass(frozen=True)
class Route:
    provider: ModelProvider
    budget: RequestBudget


class RoutedLLM:
    def __init__(
        self,
        chains: dict[Tier, list[Route]],
        fallback_enabled: bool,
        wait_deadline_seconds: float,
    ) -> None:
        self._chains = chains
        self._fallback_enabled = fallback_enabled
        self._deadline = wait_deadline_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        chain = self._chains.get(request.tier, [])
        if not self._fallback_enabled:
            chain = chain[:1]
        failures: list[str] = []
        for position, route in enumerate(chain):
            try:
                wait_ms = await route.budget.acquire(self._deadline)
                response = await route.provider.complete(request, route.budget.model)
            except RECOVERABLE as exc:
                failures.append(f"{route.provider.name}: {type(exc).__name__}")
                logger.warning("llm_route_failed", provider=route.provider.name, error=str(exc))
                continue
            response.wait_ms = wait_ms
            response.fallback = position > 0
            return response
        raise LLMUnavailable("; ".join(failures) or f"no route for tier {request.tier}")
