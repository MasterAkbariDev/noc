from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import SecretStr

from noc.api.app import create_app
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import LlmKeyStatus, LlmQuotaUsage
from noc.db.session import SessionFactory, transaction
from noc.llm.key_status import PostgresKeyStatus
from noc.llm.providers import key_label

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
KEY_ONE = "test-gemini-key-one"
KEY_TWO = "test-gemini-key-two"
LABEL_ONE = key_label("gemini", KEY_ONE)
LABEL_TWO = key_label("gemini", KEY_TWO)
GROQ_EXTRA = "groq#deadbeef"
LA_ZONE = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def gemini_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEYS", f"{KEY_ONE}\n{KEY_TWO}")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
async def llm_state(sessions: SessionFactory, gemini_keys: None) -> None:
    now = utc_now()
    today = datetime.now(LA_ZONE).date()
    async with transaction(sessions) as session:
        session.add(
            LlmKeyStatus(
                label=LABEL_ONE,
                provider="gemini",
                state="cooling",
                cooling_until=now + timedelta(minutes=1),
                last_error="ProviderRateLimited",
                last_error_at=now,
                last_success_at=now - timedelta(hours=1),
                updated_at=now,
            )
        )
        session.add(
            LlmKeyStatus(
                label=GROQ_EXTRA,
                provider="groq",
                state="rejected",
                cooling_until=now + timedelta(hours=1),
                last_error="ProviderKeyRejected",
                last_error_at=now,
                last_success_at=None,
                updated_at=now,
            )
        )
        session.add(
            LlmQuotaUsage(
                provider=LABEL_ONE, model="gemini-flash-lite-latest", day=today, requests=7
            )
        )
        session.add(
            LlmQuotaUsage(
                provider=LABEL_ONE,
                model="gemini-flash-lite-latest",
                day=today - timedelta(days=1),
                requests=500,
            )
        )


@pytest.fixture
async def client(sessions: SessionFactory, gemini_keys: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(TOKEN), llm_mode="live", _env_file=None)
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def test_llm_status_requires_the_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/system/llm")
    assert response.status_code == 401


async def test_llm_status_lists_configured_keys_then_stored_only_labels(
    client: httpx.AsyncClient, llm_state: None
) -> None:
    response = await client.get("/api/system/llm", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert [key["label"] for key in body["keys"]] == [LABEL_ONE, LABEL_TWO, GROQ_EXTRA]


async def test_configured_key_shows_state_error_and_daily_usage(
    client: httpx.AsyncClient, llm_state: None
) -> None:
    body = (await client.get("/api/system/llm", headers=AUTH)).json()
    key = body["keys"][0]
    assert key["provider"] == "gemini"
    assert key["state"] == "cooling"
    assert key["last_error"] == "ProviderRateLimited"
    assert key["cooling_until"] is not None
    assert key["last_success_at"] is not None
    assert key["models"] == [
        {
            "tier": "small",
            "model": "gemini-flash-lite-latest",
            "used_today": 7,
            "daily_limit": 800,
        },
        {"tier": "strong", "model": "gemini-flash-latest", "used_today": 0, "daily_limit": 200},
    ]


async def test_key_without_a_status_row_is_unused(
    client: httpx.AsyncClient, llm_state: None
) -> None:
    body = (await client.get("/api/system/llm", headers=AUTH)).json()
    key = body["keys"][1]
    assert key["state"] == "unused"
    assert key["cooling_until"] is None
    assert key["last_error"] is None
    assert [model["used_today"] for model in key["models"]] == [0, 0]


async def test_label_only_in_the_status_table_is_listed_with_its_provider_limits(
    client: httpx.AsyncClient, llm_state: None
) -> None:
    body = (await client.get("/api/system/llm", headers=AUTH)).json()
    key = body["keys"][2]
    assert key["label"] == GROQ_EXTRA
    assert key["provider"] == "groq"
    assert key["state"] == "rejected"
    assert key["last_error"] == "ProviderKeyRejected"
    assert [(model["tier"], model["daily_limit"]) for model in key["models"]] == [
        ("small", 900),
        ("strong", 900),
    ]


async def test_llm_status_never_contains_a_key(client: httpx.AsyncClient, llm_state: None) -> None:
    response = await client.get("/api/system/llm", headers=AUTH)
    assert KEY_ONE not in response.text
    assert KEY_TWO not in response.text
    assert "test-gemini-key" not in response.text


async def test_status_sink_writes_one_row_per_key(sessions: SessionFactory) -> None:
    sink = PostgresKeyStatus(sessions)
    cooling_until = utc_now() + timedelta(seconds=60)
    await sink.record_failure(
        "gemini#abc12345", "gemini", "cooling", cooling_until, "QuotaExhausted"
    )
    await sink.record_success("gemini#abc12345", "gemini")
    async with sessions() as session:
        row = await session.get(LlmKeyStatus, "gemini#abc12345")
    assert row is not None
    assert row.state == "ok"
    assert row.cooling_until is None
    assert row.last_error == "QuotaExhausted"
    assert row.last_error_at is not None
    assert row.last_success_at is not None
