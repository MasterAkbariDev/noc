from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from noc.api.app import create_app
from noc.audit.chain import append_audit
from noc.config import Settings
from noc.db.models import AuditEntry
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
INCIDENT_ID = "3f2a9c10-6b7e-4d2a-9f11-0c5e7a8b9d01"


async def record(
    sessions: SessionFactory, actor: str, action: str, subject: str, payload: dict[str, Any]
) -> None:
    async with transaction(sessions) as session:
        await append_audit(session, actor, action, subject, payload)


@pytest.fixture
async def client(sessions: SessionFactory) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(TOKEN))
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


@pytest.fixture
async def trail(sessions: SessionFactory) -> None:
    await record(sessions, "alice", "login", "alice", {})
    await record(sessions, "bob", "login_failed", "bob", {})
    await record(
        sessions, "alice", "incident_closed", INCIDENT_ID, {"corrected_root_cause_code": None}
    )
    await record(sessions, "cli", "target_added", "lab-1", {"env": "lab"})
    await record(sessions, "alice", "user_created", "user:carol", {"role": "viewer"})


async def entry_ids_of_action(sessions: SessionFactory, action: str) -> list[int]:
    async with sessions() as session:
        return list(await session.scalars(select(AuditEntry.id).where(AuditEntry.action == action)))


async def test_activity_requires_token(client: httpx.AsyncClient, trail: None) -> None:
    assert (await client.get("/api/activity")).status_code == 401
    assert (
        await client.get("/api/activity", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401
    assert (await client.get("/api/activity/verify")).status_code == 401


async def test_pages_are_newest_first_without_overlap(
    client: httpx.AsyncClient, trail: None
) -> None:
    seen: list[int] = []
    cursor: int | None = None
    pages = 0
    while True:
        params: dict[str, int] = {"limit": 2}
        if cursor is not None:
            params["before_id"] = cursor
        body = (await client.get("/api/activity", params=params, headers=AUTH)).json()
        seen.extend(item["id"] for item in body["items"])
        pages += 1
        cursor = body["next_before_id"]
        if cursor is None:
            break
    assert pages == 3
    assert len(seen) == 5
    assert len(set(seen)) == 5
    assert seen == sorted(seen, reverse=True)


async def test_default_limit_returns_every_entry_and_no_cursor(
    client: httpx.AsyncClient, trail: None
) -> None:
    body = (await client.get("/api/activity", headers=AUTH)).json()
    assert len(body["items"]) == 5
    assert body["next_before_id"] is None


async def test_limit_outside_one_to_two_hundred_is_rejected(
    client: httpx.AsyncClient, trail: None
) -> None:
    assert (await client.get("/api/activity", params={"limit": 0}, headers=AUTH)).status_code == 422
    assert (
        await client.get("/api/activity", params={"limit": 201}, headers=AUTH)
    ).status_code == 422


async def test_action_and_actor_filters_narrow_the_list(
    client: httpx.AsyncClient, trail: None
) -> None:
    by_action = (
        await client.get("/api/activity", params={"action": "login_failed"}, headers=AUTH)
    ).json()
    assert [item["actor"] for item in by_action["items"]] == ["bob"]
    by_actor = (await client.get("/api/activity", params={"actor": "alice"}, headers=AUTH)).json()
    assert [item["action"] for item in by_actor["items"]] == [
        "user_created",
        "incident_closed",
        "login",
    ]
    both = (
        await client.get(
            "/api/activity", params={"actor": "alice", "action": "login"}, headers=AUTH
        )
    ).json()
    assert [item["action"] for item in both["items"]] == ["login"]


async def test_entries_carry_labels_and_plain_sentences(
    client: httpx.AsyncClient, trail: None
) -> None:
    items = (await client.get("/api/activity", headers=AUTH)).json()["items"]
    by_action = {item["action"]: item for item in items}
    closed = by_action["incident_closed"]
    assert closed["action_label"] == "Incident closed"
    assert closed["subject"] == INCIDENT_ID
    assert closed["summary"] == "alice closed incident 3f2a9c10…"
    assert by_action["login_failed"]["summary"] == "Failed sign-in for bob"
    assert by_action["user_created"]["summary"] == "alice created the user carol"
    assert by_action["user_created"]["payload"] == {"role": "viewer"}
    assert by_action["target_added"]["summary"] == "cli added the target lab-1"


async def test_unknown_action_falls_back_to_a_humanized_label(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await record(sessions, "cli", "future_action", "thing", {})
    items = (await client.get("/api/activity", headers=AUTH)).json()["items"]
    assert items[0]["action_label"] == "Future action"
    assert items[0]["summary"] == "Future action by cli: thing"


async def test_verify_reports_an_intact_chain(client: httpx.AsyncClient, trail: None) -> None:
    body = (await client.get("/api/activity/verify", headers=AUTH)).json()
    assert body == {"ok": True, "broken_at": None}


async def test_verify_points_at_a_tampered_row(
    client: httpx.AsyncClient, sessions: SessionFactory, trail: None
) -> None:
    (tampered_id,) = await entry_ids_of_action(sessions, "incident_closed")
    async with transaction(sessions) as session:
        await session.execute(
            update(AuditEntry)
            .where(AuditEntry.id == tampered_id)
            .values(payload={"corrected_root_cause_code": "memory_leak"})
        )
    body = (await client.get("/api/activity/verify", headers=AUTH)).json()
    assert body == {"ok": False, "broken_at": tampered_id}
