from typing import cast

import openai as openai_module
import pytest

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.client import (
    LLMUnavailable,
    ProviderKeyRejected,
    ProviderRateLimited,
)
from noc.llm.factory import build_routed_llm, openai_client
from noc.llm.fake import answer
from noc.llm.providers import ProviderConfig, key_label
from noc.llm.ratelimit import MemoryQuotaStore, RequestBudget
from noc.llm.router import Route, RoutedLLM
from noc.llm.types import CallContext, ChatMessage, LLMRequest, LLMResponse, Role


class StubProvider:
    def __init__(self, name: str, errors: list[Exception] | None = None) -> None:
        self.name = name
        self.errors = list(errors or [])
        self.calls = 0

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        response = answer("{}")
        response.provider = self.name
        response.model = model
        return response


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def route(provider: StubProvider, label: str, per_day: int = 100) -> Route:
    budget = RequestBudget(label, f"{provider.name}-model", 600, per_day, "UTC", MemoryQuotaStore())
    return Route(provider, budget, label)


def routed(routes: list[Route], fallback: bool = True, time: FakeTime | None = None) -> RoutedLLM:
    clock = time or FakeTime()
    return RoutedLLM({"small": routes}, fallback, 5, clock=clock.clock, sleep=clock.sleep)


REQUEST = LLMRequest(
    tier="small",
    messages=[ChatMessage(role=Role.USER, content="hi")],
    context=CallContext(agent="test"),
)


async def test_primary_provider_is_used_first() -> None:
    gemini, groq = StubProvider("gemini"), StubProvider("groq")
    response = await routed([route(gemini, "g#1"), route(groq, "q#1")]).complete(REQUEST)
    assert response.provider == "gemini"
    assert not response.fallback
    assert groq.calls == 0


async def test_rate_limited_key_rotates_to_the_next_key_of_the_same_provider() -> None:
    first = StubProvider("gemini", [ProviderRateLimited("429")])
    second = StubProvider("gemini")
    response = await routed([route(first, "g#1"), route(second, "g#2")]).complete(REQUEST)
    assert response.provider == "gemini"
    assert not response.fallback
    assert second.calls == 1


async def test_cooling_key_is_skipped_on_the_next_request() -> None:
    first = StubProvider("gemini", [ProviderRateLimited("429")])
    second = StubProvider("gemini")
    llm = routed([route(first, "g#1"), route(second, "g#2")])
    await llm.complete(REQUEST)
    await llm.complete(REQUEST)
    assert first.calls == 1
    assert second.calls == 2


async def test_cooled_key_is_used_again_after_its_cooldown() -> None:
    time = FakeTime()
    first = StubProvider("gemini", [ProviderRateLimited("429")])
    second = StubProvider("gemini")
    llm = routed([route(first, "g#1"), route(second, "g#2")], time=time)
    await llm.complete(REQUEST)
    time.now += 61
    await llm.complete(REQUEST)
    assert first.calls == 2


async def test_rejected_key_stays_out_for_an_hour() -> None:
    time = FakeTime()
    bad = StubProvider("gemini", [ProviderKeyRejected("401")])
    good = StubProvider("gemini")
    llm = routed([route(bad, "g#bad"), route(good, "g#ok")], time=time)
    await llm.complete(REQUEST)
    time.now += 600
    await llm.complete(REQUEST)
    assert bad.calls == 1
    assert good.calls == 2


async def test_other_provider_is_used_when_all_keys_fail() -> None:
    keys = [StubProvider("gemini", [ProviderRateLimited("429")]) for _ in range(2)]
    groq = StubProvider("groq")
    routes = [route(keys[0], "g#1"), route(keys[1], "g#2"), route(groq, "q#1")]
    response = await routed(routes).complete(REQUEST)
    assert response.provider == "groq"
    assert response.fallback


async def test_evaluation_mode_rotates_keys_but_never_changes_provider() -> None:
    first = StubProvider("gemini", [ProviderRateLimited("429")])
    second = StubProvider("gemini", [ProviderRateLimited("429")])
    groq = StubProvider("groq")
    llm = routed([route(first, "g#1"), route(second, "g#2"), route(groq, "q#1")], fallback=False)
    with pytest.raises(LLMUnavailable):
        await llm.complete(REQUEST)
    assert (first.calls, second.calls, groq.calls) == (1, 1, 0)


async def test_short_cooldown_is_waited_out_within_the_deadline() -> None:
    time = FakeTime()
    only = StubProvider("gemini", [ProviderRateLimited("429")])
    llm = RoutedLLM({"small": [route(only, "g#1")]}, True, 120, clock=time.clock, sleep=time.sleep)
    with pytest.raises(LLMUnavailable):
        await llm.complete(REQUEST)
    response = await llm.complete(REQUEST)
    assert response.provider == "gemini"
    assert time.slept == [60.0]


async def test_long_cooldown_fails_fast() -> None:
    only = StubProvider("gemini", [ProviderKeyRejected("401")])
    llm = routed([route(only, "g#1")])
    with pytest.raises(LLMUnavailable):
        await llm.complete(REQUEST)
    with pytest.raises(LLMUnavailable, match="cooling down"):
        await llm.complete(REQUEST)
    assert only.calls == 1


async def test_daily_quota_is_enforced_before_calling() -> None:
    gemini, groq = StubProvider("gemini"), StubProvider("groq")
    llm = routed([route(gemini, "g#1", per_day=1), route(groq, "q#1")])
    first = await llm.complete(REQUEST)
    second = await llm.complete(REQUEST)
    assert (first.provider, second.provider) == ("gemini", "groq")
    assert gemini.calls == 1


def test_keys_are_read_from_both_variables_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_KEYS", "k1, k2\nk3;k1")
    monkeypatch.setenv("TEST_KEY", "k2")
    config = ProviderConfig(
        base_url="https://x", api_key_env="TEST_KEY", api_keys_env="TEST_KEYS", models={}
    )
    assert config.api_keys() == ["k1", "k2", "k3"]


def test_one_quoted_key_per_line_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_KEYS", '"key-one\nkey-two\n  key-three\n"')
    monkeypatch.delenv("TEST_KEY", raising=False)
    config = ProviderConfig(
        base_url="https://x", api_key_env="TEST_KEY", api_keys_env="TEST_KEYS", models={}
    )
    assert config.api_keys() == ["key-one", "key-two", "key-three"]


def test_key_labels_never_contain_the_key() -> None:
    label = key_label("gemini", "AIzaSecretValue123")
    assert label.startswith("gemini#")
    assert "Secret" not in label


def test_factory_builds_one_route_per_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEYS", "a1,a2")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "b1")
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    llm = build_routed_llm(Settings(_env_file=None), cast(SessionFactory, None))
    labels = [route.label for route in llm.routes_for("strong")]
    assert len(labels) == 3
    assert [label.split("#")[0] for label in labels] == ["gemini", "gemini", "groq"]


def test_proxy_is_read_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROXY", " http://127.0.0.1:10950 ")
    with_proxy = ProviderConfig(
        base_url="https://x", api_key_env="K", proxy_env="TEST_PROXY", models={}
    )
    without = ProviderConfig(base_url="https://x", api_key_env="K", models={})
    assert with_proxy.proxy_url() == "http://127.0.0.1:10950"
    assert without.proxy_url() is None


def test_gemini_client_is_built_with_its_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOC_GEMINI_PROXY", "http://127.0.0.1:10950")
    created: list[dict[str, object]] = []
    original = openai_module.DefaultAsyncHttpxClient

    def spy(**kwargs: object) -> object:
        created.append(kwargs)
        return original()

    monkeypatch.setattr(openai_module, "DefaultAsyncHttpxClient", spy)
    config = ProviderConfig(
        base_url="https://x", api_key_env="K", proxy_env="NOC_GEMINI_PROXY", models={}
    )
    openai_client(config, "key")
    assert created == [{"proxy": "http://127.0.0.1:10950"}]


def test_llm_requests_have_a_bounded_timeout() -> None:
    config = ProviderConfig(base_url="https://x", api_key_env="K", models={})
    assert openai_client(config, "key", 42.0).timeout == 42.0
