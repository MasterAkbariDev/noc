import os
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.users import create_user
from noc.config import Settings
from noc.db.models import AuditEntry, LlmKey, NocSetting
from noc.db.session import SessionFactory, transaction
from noc.llm.client import LLMClient
from noc.llm.key_check import CheckResult
from noc.llm.keys import KeyEntry, add_key, key_secret_name, revoke_key, set_proxy
from noc.llm.providers import key_label, load_providers
from noc.llm.reloading import ReloadingLLM
from noc.llm.types import CallContext, ChatMessage, LLMRequest, LLMResponse, Tier
from noc.llm.types import Role as MessageRole
from noc.secret_store import SecretStore

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SECRET = "AIza-test-secret-value-1234"
GROQ_SECRET = "gsk_test_secret_value_5678"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def no_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GEMINI_API_KEYS", "GEMINI_API_KEY", "GROQ_API_KEYS", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("NOC_GEMINI_PROXY", raising=False)
    monkeypatch.delenv("NOC_GROQ_PROXY", raising=False)


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        secrets_dir=tmp_path / "secrets",
        llm_mode="live",
        _env_file=None,
    )


@pytest.fixture
async def client(sessions: SessionFactory, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tickets = TicketStore()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def add(client: httpx.AsyncClient, **changes: Any) -> httpx.Response:
    body = {"provider": "gemini", "tier": "free", "name": "main", "secret": SECRET, **changes}
    return await client.post("/api/llm/keys", json=body, headers=AUTH)


async def audit_rows(sessions: SessionFactory) -> list[tuple[str, dict[str, Any]]]:
    async with sessions() as session:
        rows = await session.execute(
            select(AuditEntry.action, AuditEntry.payload, AuditEntry.subject).order_by(
                AuditEntry.id
            )
        )
        return [(row.action, {**row.payload, "subject": row.subject}) for row in rows]


async def test_adding_a_key_stores_the_secret_in_a_file_and_never_echoes_it(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    response = await add(client, tier="paid", name="paid gemini")
    assert response.status_code == 200
    body = response.json()
    assert SECRET not in response.text
    assert body["last4"] == SECRET[-4:]
    assert body["tier"] == "paid"
    assert body["source"] == "panel"
    assert body["label"] == key_label("gemini", SECRET)

    store = SecretStore(settings.secrets_dir)
    path = store.path_for(key_secret_name(body["id"]))
    assert path.read_text() == SECRET
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    async with sessions() as session:
        row = await session.scalar(select(LlmKey))
    assert row is not None
    assert SECRET not in str(row.__dict__)
    audit = await audit_rows(sessions)
    assert "llm_key_added" in [action for action, _ in audit]
    assert all(SECRET not in str(payload) for _, payload in audit)


async def test_config_lists_providers_proxies_and_keys(client: httpx.AsyncClient) -> None:
    await add(client)
    response = await client.get("/api/llm/config", headers=AUTH)
    assert response.status_code == 200
    config = response.json()
    assert [p["name"] for p in config["providers"]] == ["gemini", "groq"]
    gemini = config["providers"][0]
    assert gemini["proxy"] == {"display": None, "source": "none"}
    assert {m["tier"] for m in gemini["paid_models"]} == {"small", "strong"}
    assert [(k["provider"], k["source"], k["name"]) for k in config["keys"]] == [
        ("gemini", "panel", "main")
    ]
    assert SECRET not in response.text


async def test_env_keys_are_listed_as_read_only_entries(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", GROQ_SECRET)
    config = (await client.get("/api/llm/config", headers=AUTH)).json()
    assert [(k["provider"], k["source"], k["id"]) for k in config["keys"]] == [
        ("groq", "env", None)
    ]
    assert GROQ_SECRET not in str(config)


async def test_the_same_key_cannot_be_added_twice_even_if_it_is_in_the_environment(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await add(client)).status_code == 200
    again = await add(client, name="copy")
    assert again.status_code == 422
    assert "already configured" in again.json()["detail"]
    monkeypatch.setenv("GROQ_API_KEY", GROQ_SECRET)
    env_copy = await add(client, provider="groq", secret=GROQ_SECRET)
    assert env_copy.status_code == 422


async def test_bad_keys_are_refused_with_the_reason(client: httpx.AsyncClient) -> None:
    unknown = await add(client, provider="openai")
    short = await add(client, secret="abc")
    assert unknown.status_code == 422
    assert "unknown provider" in unknown.json()["detail"]
    assert short.status_code == 422


async def test_revoking_deletes_the_secret_file_and_hides_the_key(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    created = (await add(client)).json()
    removed = await client.delete(f"/api/llm/keys/{created['id']}", headers=AUTH)
    assert removed.status_code == 204
    store = SecretStore(settings.secrets_dir)
    assert store.read(key_secret_name(created["id"])) is None
    config = (await client.get("/api/llm/config", headers=AUTH)).json()
    assert config["keys"] == []
    async with sessions() as session:
        row = await session.scalar(select(LlmKey))
    assert row is not None
    assert row.revoked_at is not None
    assert row.revoked_by == "api-token"
    again = await client.delete(f"/api/llm/keys/{created['id']}", headers=AUTH)
    assert again.status_code == 404


async def test_proxy_is_stored_as_a_secret_and_shown_without_credentials(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    url = "http://user:hunter2@10.0.0.9:3128"
    response = await client.put("/api/llm/providers/gemini/proxy", json={"url": url}, headers=AUTH)
    assert response.status_code == 200
    gemini = response.json()["providers"][0]
    assert gemini["proxy"] == {"display": "http://***@10.0.0.9:3128", "source": "panel"}
    assert "hunter2" not in response.text
    assert SecretStore(settings.secrets_dir).read("llm-proxy-gemini") == url
    async with sessions() as session:
        setting = await session.get(NocSetting, "llm.proxy.gemini")
    assert setting is not None
    assert "hunter2" not in str(setting.value)


async def test_a_panel_proxy_overrides_the_environment_and_reset_returns_to_it(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOC_GEMINI_PROXY", "http://10.1.1.1:8080")
    before = (await client.get("/api/llm/config", headers=AUTH)).json()["providers"][0]
    assert before["proxy"] == {"display": "http://10.1.1.1:8080", "source": "env"}
    cleared = await client.put("/api/llm/providers/gemini/proxy", json={"url": None}, headers=AUTH)
    assert cleared.json()["providers"][0]["proxy"] == {"display": None, "source": "none"}
    reset = await client.delete("/api/llm/providers/gemini/proxy", headers=AUTH)
    assert reset.json()["providers"][0]["proxy"]["source"] == "env"


async def test_bad_proxies_and_unknown_providers_are_refused(client: httpx.AsyncClient) -> None:
    socks = await client.put(
        "/api/llm/providers/gemini/proxy", json={"url": "socks5://h:1"}, headers=AUTH
    )
    unknown = await client.put(
        "/api/llm/providers/openai/proxy", json={"url": "http://h:1"}, headers=AUTH
    )
    assert socks.status_code == 422
    assert unknown.status_code == 404


async def test_checking_a_key_uses_that_key_and_reports_the_answer(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = (await add(client)).json()
    seen: list[str] = []

    class FakeProvider:
        def __init__(self, name: str, client: object, extra: object = None) -> None:
            self.name = name

        async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
            seen.append(model)
            return LLMResponse(content="OK", provider=self.name, model=model, latency_ms=5)

    monkeypatch.setattr("noc.api.llm_admin.OpenAICompatProvider", FakeProvider)
    response = await client.post(
        "/api/llm/keys/check", json={"label": created["label"]}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["detail"] == "answered: OK"
    assert len(seen) == 1
    status = (await client.get("/api/system/llm", headers=AUTH)).json()
    key = next(k for k in status["keys"] if k["label"] == created["label"])
    assert key["state"] == "ok"
    assert sum(model["used_today"] for model in key["models"]) == 1


async def test_checking_an_unknown_label_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/llm/keys/check", json={"label": "gemini#0"}, headers=AUTH)
    assert response.status_code == 404


async def test_checking_a_proxy_needs_one(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/llm/providers/gemini/proxy/check", headers=AUTH)
    assert response.status_code == 409


async def test_system_llm_shows_panel_keys_with_their_tier(client: httpx.AsyncClient) -> None:
    created = (await add(client, tier="paid")).json()
    status = (await client.get("/api/system/llm", headers=AUTH)).json()
    key = next(k for k in status["keys"] if k["label"] == created["label"])
    assert key["tier"] == "paid"
    assert all(model["daily_limit"] >= 10000 for model in key["models"])


async def test_viewers_and_operators_cannot_manage_llm_keys(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "olivia", PASSWORD, Role.OPERATOR, "cli")
    await client.post("/api/auth/login", json={"username": "olivia", "password": PASSWORD})
    csrf = {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}
    assert (await client.get("/api/llm/config")).status_code == 403
    response = await client.post(
        "/api/llm/keys",
        json={"provider": "gemini", "name": "x", "secret": SECRET},
        headers=csrf,
    )
    assert response.status_code == 403


class CountingBuilder:
    def __init__(self) -> None:
        self.builds: list[list[str]] = []

    def __call__(
        self,
        keys: list[KeyEntry],
        proxies: dict[str, str | None],
        chains: dict[Tier, list[str]],
    ) -> LLMClient:
        self.builds.append([key.label for key in keys])
        return cast(LLMClient, EchoClient())


class EchoClient:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="echo")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


REQUEST = LLMRequest(
    tier="small",
    messages=[ChatMessage(role=MessageRole.USER, content="hi")],
    context=CallContext(agent="test"),
)


async def test_the_worker_picks_up_new_and_revoked_keys_without_a_restart(
    sessions: SessionFactory, settings: Settings
) -> None:
    store = SecretStore(settings.secrets_dir)
    document = load_providers(settings.llm_providers_file)
    builder = CountingBuilder()
    clock = FakeClock()
    llm = ReloadingLLM(settings, sessions, store, builder, clock)

    await llm.complete(REQUEST)
    assert builder.builds == [[]]

    async with transaction(sessions) as session:
        row = await add_key(session, store, document, "gemini", SECRET, "free", "k", "test")
    clock.now += 1
    await llm.complete(REQUEST)
    assert len(builder.builds) == 1

    clock.now += settings.llm_reload_seconds
    await llm.complete(REQUEST)
    assert builder.builds[-1] == [key_label("gemini", SECRET)]

    clock.now += settings.llm_reload_seconds
    await llm.complete(REQUEST)
    assert len(builder.builds) == 2

    async with transaction(sessions) as session:
        await revoke_key(session, store, row.id, "test")
        await set_proxy(session, store, document, "groq", "http://10.0.0.1:1", "test")
    clock.now += settings.llm_reload_seconds
    await llm.complete(REQUEST)
    assert builder.builds[-1] == []
    assert len(builder.builds) == 3


async def test_checking_all_proxies_checks_only_the_providers_that_have_one(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check(base_url: str, proxy: str) -> CheckResult:
        return CheckResult(True, 7, None, f"reached via {proxy}")

    monkeypatch.setattr("noc.api.llm_admin.check_proxy", fake_check)
    await client.put(
        "/api/llm/providers/gemini/proxy", json={"url": "http://10.0.0.9:3128"}, headers=AUTH
    )
    response = await client.post("/api/llm/proxies/check", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == [
        {
            "provider": "gemini",
            "ok": True,
            "latency_ms": 7,
            "model": None,
            "detail": "reached via http://10.0.0.9:3128",
        }
    ]


async def test_checking_all_proxies_with_none_set_checks_nothing(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/llm/proxies/check", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == []


async def test_the_model_order_can_be_changed_and_reset(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    changed = await client.put(
        "/api/llm/chains/small",
        json={"entries": ["gemini:strong", "groq:small"]},
        headers=AUTH,
    )
    assert changed.status_code == 200
    small = next(chain for chain in changed.json()["chains"] if chain["tier"] == "small")
    assert [entry["entry"] for entry in small["entries"]] == ["gemini:strong", "groq:small"]
    assert small["entries"][0]["degraded"] is True
    assert small["entries"][1]["degraded"] is False
    assert small["customized"] is True
    strong = next(chain for chain in changed.json()["chains"] if chain["tier"] == "strong")
    assert strong["customized"] is False

    reset = await client.delete("/api/llm/chains/small", headers=AUTH)
    small = next(chain for chain in reset.json()["chains"] if chain["tier"] == "small")
    assert [entry["entry"] for entry in small["entries"]] == [
        "groq:small",
        "gemini:small",
        "gemini:strong",
    ]
    assert small["customized"] is False
    async with sessions() as session:
        assert await session.get(NocSetting, "llm.chain.small") is None


async def test_a_model_order_only_names_models_listed_once_in_the_providers_file(
    client: httpx.AsyncClient,
) -> None:
    unknown = await client.put(
        "/api/llm/chains/small", json={"entries": ["openai:small"]}, headers=AUTH
    )
    repeated = await client.put(
        "/api/llm/chains/small", json={"entries": ["groq:small", "groq:small"]}, headers=AUTH
    )
    empty = await client.put("/api/llm/chains/small", json={"entries": []}, headers=AUTH)
    assert unknown.status_code == 422
    assert repeated.status_code == 422
    assert empty.status_code == 422
