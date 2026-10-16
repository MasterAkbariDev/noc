import os
import stat
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from noc.config import PACKAGE_DIR, Settings
from noc.db.session import SessionFactory
from noc.llm.client import ProviderKeyRejected, ProviderRateLimited, ProviderUnavailable
from noc.llm.factory import build_routed_llm
from noc.llm.key_check import check_key, scrub
from noc.llm.keys import (
    KeyEntry,
    KeyRefused,
    check_new_key,
    check_proxy,
    display_proxy,
    ordered,
)
from noc.llm.providers import ProviderConfig, load_providers
from noc.llm.ratelimit import MemoryQuotaStore
from noc.llm.types import LLMRequest, LLMResponse
from noc.secret_store import SecretStore

DOCUMENT = load_providers(PACKAGE_DIR / "llm" / "providers.yaml")
GEMINI = DOCUMENT.providers["gemini"]


def entry(secret: str, tier: str = "free", provider: str = "gemini") -> KeyEntry:
    return KeyEntry(provider, secret, "paid" if tier == "paid" else "free", "panel")


class StubProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.models: list[str] = []

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        self.models.append(model)
        if self.error is not None:
            raise self.error
        return LLMResponse(content=" OK ", provider="gemini", model=model, latency_ms=12)


class RecordingStatus:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def record_success(self, label: str, provider: str) -> None:
        self.events.append(("ok", label))

    async def record_failure(
        self,
        label: str,
        provider: str,
        state: str,
        cooling_until: datetime | None,
        error_name: str,
    ) -> None:
        self.events.append((state, label))


def test_secret_store_writes_owner_only_files_and_reads_them_back(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets")
    store.write("llm-key-one", "abc123")
    path = store.path_for("llm-key-one")
    assert path.read_text() == "abc123"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(tmp_path / "secrets").st_mode) == 0o700
    assert store.read("llm-key-one") == "abc123"
    store.write("llm-key-one", "new-value")
    assert store.read("llm-key-one") == "new-value"
    store.delete("llm-key-one")
    assert store.read("llm-key-one") is None
    store.delete("llm-key-one")
    assert [p.name for p in (tmp_path / "secrets").iterdir()] == []


@pytest.mark.parametrize("name", ["../x", "UPPER", "a/b", "", "-lead", "x" * 81, "dot.name"])
def test_secret_names_cannot_escape_or_surprise(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="invalid secret name"):
        SecretStore(tmp_path).path_for(name)


@pytest.mark.parametrize(
    ("provider", "secret", "name", "message"),
    [
        ("nope", "abcdefgh1234", "k", "unknown provider"),
        ("gemini", "short", "k", "8-256"),
        ("gemini", "has space in it", "k", "8-256"),
        ("gemini", "abcdefgh1234", " ", "name"),
        ("gemini", "abcdefgh1234", "x" * 65, "name"),
    ],
)
def test_new_keys_are_checked(provider: str, secret: str, name: str, message: str) -> None:
    with pytest.raises(KeyRefused, match=message):
        check_new_key(DOCUMENT, provider, secret, name)


def test_a_valid_new_key_passes() -> None:
    check_new_key(DOCUMENT, "groq", "gsk_abcdefgh12345678", "main groq key")


@pytest.mark.parametrize("url", ["socks5://h:1", "ftp://h", "http://", "not a url", "file:///x"])
def test_only_http_proxies_with_a_host_are_accepted(url: str) -> None:
    with pytest.raises(KeyRefused):
        check_proxy(url)


def test_proxy_display_hides_credentials() -> None:
    assert display_proxy("http://user:pass@10.0.0.1:3128") == "http://***@10.0.0.1:3128"
    assert display_proxy("https://proxy.example") == "https://proxy.example"
    assert display_proxy(None) is None


def test_paid_keys_come_before_free_keys() -> None:
    keys = [entry("free-1"), entry("paid-1", "paid"), entry("free-2")]
    assert [key.secret for key in ordered(keys)] == ["paid-1", "free-1", "free-2"]


def test_limits_follow_the_key_tier() -> None:
    free = GEMINI.limits_for("small", "free")
    paid = GEMINI.limits_for("small", "paid")
    assert free is not None
    assert paid is not None
    assert paid.rpd > free.rpd
    no_paid = ProviderConfig(base_url="https://x", api_key_env="K", models=dict(GEMINI.models))
    assert no_paid.limits_for("small", "paid") == no_paid.limits_for("small", "free")


def test_factory_builds_routes_from_given_keys_with_their_tier_limits() -> None:
    keys = [entry("gemini-paid-key", "paid"), entry("gemini-free-key")]
    llm = build_routed_llm(Settings(_env_file=None), cast(SessionFactory, None), keys, {})
    small = llm.routes_for("small")
    assert [route.label for route in small] == [keys[0].label, keys[1].label]
    paid_limits = GEMINI.limits_for("small", "paid")
    assert paid_limits is not None
    assert small[0].budget.model == paid_limits.model


def test_factory_with_no_keys_has_no_routes() -> None:
    llm = build_routed_llm(Settings(_env_file=None), cast(SessionFactory, None), [], {})
    assert llm.routes_for("small") == []


def test_scrub_removes_the_secret_from_error_text() -> None:
    assert scrub("bad key sk-123456 rejected", "sk-123456") == "bad key *** rejected"


async def test_check_key_answers_and_records_success() -> None:
    provider = StubProvider()
    status = RecordingStatus()
    key = entry("gemini-test-key")
    result = await check_key(key, GEMINI, lambda _c, _k: provider, MemoryQuotaStore(), status)
    assert result.ok
    assert result.detail == "answered: OK"
    small = GEMINI.limits_for("small", "free")
    assert small is not None
    assert provider.models == [small.model]
    assert status.events == [("ok", key.label)]


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (ProviderKeyRejected("401 for key gemini-test-key"), "rejected"),
        (ProviderRateLimited("429"), "cooling"),
        (ProviderUnavailable("503"), None),
    ],
)
async def test_check_key_reports_failures_without_the_secret(
    error: Exception, state: str | None
) -> None:
    status = RecordingStatus()
    key = entry("gemini-test-key")
    result = await check_key(
        key, GEMINI, lambda _c, _k: StubProvider(error), MemoryQuotaStore(), status
    )
    assert not result.ok
    assert "gemini-test-key" not in result.detail
    assert type(error).__name__ in result.detail
    assert status.events == ([] if state is None else [(state, key.label)])


def provider_today() -> date:
    return datetime.now(ZoneInfo(GEMINI.quota_timezone)).date()


async def test_check_key_respects_the_daily_quota() -> None:
    quota = MemoryQuotaStore()
    key = entry("gemini-test-key")
    small = GEMINI.limits_for("small", "free")
    assert small is not None
    for _ in range(small.rpd):
        await quota.reserve(key.label, small.model, provider_today(), small.rpd)
    provider = StubProvider()
    result = await check_key(key, GEMINI, lambda _c, _k: provider, quota, RecordingStatus())
    assert not result.ok
    assert "quota" in result.detail
    assert provider.models == []
