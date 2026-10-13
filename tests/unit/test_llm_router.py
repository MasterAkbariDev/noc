import pytest

from noc.llm.client import LLMUnavailable, ProviderRateLimited
from noc.llm.fake import answer
from noc.llm.ratelimit import MemoryQuotaStore, RequestBudget
from noc.llm.router import Route, RoutedLLM
from noc.llm.types import CallContext, ChatMessage, LLMRequest, LLMResponse, Role


class StubProvider:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        self.calls += 1
        if self.fail:
            raise ProviderRateLimited("429")
        response = answer("{}")
        response.provider = self.name
        response.model = model
        return response


def route(provider: StubProvider, per_day: int = 100) -> Route:
    budget = RequestBudget(
        provider.name, f"{provider.name}-model", 60, per_day, "UTC", MemoryQuotaStore()
    )
    return Route(provider, budget)


REQUEST = LLMRequest(
    tier="small",
    messages=[ChatMessage(role=Role.USER, content="hi")],
    context=CallContext(agent="test"),
)


async def test_primary_provider_is_used_first() -> None:
    gemini, groq = StubProvider("gemini"), StubProvider("groq")
    llm = RoutedLLM({"small": [route(gemini), route(groq)]}, True, 5)
    response = await llm.complete(REQUEST)
    assert response.provider == "gemini"
    assert not response.fallback
    assert groq.calls == 0


async def test_rate_limit_falls_back_to_next_provider() -> None:
    gemini, groq = StubProvider("gemini", fail=True), StubProvider("groq")
    llm = RoutedLLM({"small": [route(gemini), route(groq)]}, True, 5)
    response = await llm.complete(REQUEST)
    assert response.provider == "groq"
    assert response.fallback


async def test_fallback_can_be_disabled_for_evaluation() -> None:
    gemini, groq = StubProvider("gemini", fail=True), StubProvider("groq")
    llm = RoutedLLM({"small": [route(gemini), route(groq)]}, False, 5)
    with pytest.raises(LLMUnavailable):
        await llm.complete(REQUEST)
    assert groq.calls == 0


async def test_daily_quota_is_enforced_before_calling() -> None:
    gemini, groq = StubProvider("gemini"), StubProvider("groq")
    llm = RoutedLLM({"small": [route(gemini, per_day=1), route(groq)]}, True, 5)
    first = await llm.complete(REQUEST)
    second = await llm.complete(REQUEST)
    assert (first.provider, second.provider) == ("gemini", "groq")
    assert gemini.calls == 1
