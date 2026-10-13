import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from noc.api.app import create_app
from noc.config import Settings
from noc.db.models import Incident
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import IncidentStatus
from noc.policy.models import Environment
from noc.store.incidents import add_event
from noc.store.targets import add_target

pytestmark = pytest.mark.integration

TOKEN = "t"
STREAM_PATH = "/api/events/stream"


@dataclass
class StreamProbe:
    chunks: asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    disconnect: asyncio.Event = field(default_factory=asyncio.Event)
    status: list[int] = field(default_factory=list)

    async def receive(self) -> dict[str, Any]:
        await self.disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status.append(message["status"])
        elif message["type"] == "http.response.body":
            body: bytes = message.get("body", b"")
            if body:
                await self.chunks.put(body)

    async def next_text(self, seconds: float) -> str:
        async with asyncio.timeout(seconds):
            return (await self.chunks.get()).decode()


def stream_scope() -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": STREAM_PATH,
        "raw_path": STREAM_PATH.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"authorization", f"Bearer {TOKEN}".encode())],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }


async def open_stream(app: FastAPI) -> tuple[StreamProbe, asyncio.Task[None]]:
    probe = StreamProbe()
    task = asyncio.create_task(app(stream_scope(), probe.receive, probe.send))
    return probe, task


@pytest.fixture
async def app(sessions: SessionFactory, database_url: str) -> AsyncIterator[FastAPI]:
    settings = Settings(database_url=database_url, api_token=TOKEN)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


async def create_incident(sessions: SessionFactory) -> uuid.UUID:
    async with transaction(sessions) as session:
        target = await add_target(
            session,
            "stream-target",
            "10.0.0.5",
            "https://10.0.0.5:9443",
            Environment.LAB,
            "k1",
        )
        incident = Incident(
            target_id=target.id,
            status=IncidentStatus.NEW.value,
            severity="warning",
            title="stream test",
            trace_id=uuid.uuid4().hex,
        )
        session.add(incident)
        await session.flush()
        return incident.id


async def test_event_arrives_within_two_seconds(app: FastAPI, sessions: SessionFactory) -> None:
    probe, task = await open_stream(app)
    try:
        assert await probe.next_text(seconds=5) == ": connected\n\n"
        assert probe.status == [200]
        incident_id = await create_incident(sessions)
        async with transaction(sessions) as session:
            event = await add_event(session, incident_id, "note_added", "tester", {"n": 1})
            expected_id = event.id
        async with asyncio.timeout(2):
            frame = await probe.next_text(seconds=2)
    finally:
        probe.disconnect.set()
        await task
    assert frame.startswith("event: incident_event\ndata: ")
    data = json.loads(frame.split("data: ", 1)[1].strip())
    assert data == {
        "incident_id": str(incident_id),
        "id": expected_id,
        "ts": data["ts"],
        "type": "note_added",
        "actor": "tester",
        "payload": {"n": 1},
    }


async def test_stream_requires_token(app: FastAPI) -> None:
    probe = StreamProbe()
    scope = stream_scope()
    scope["headers"] = []
    await asyncio.wait_for(app(scope, probe.receive, probe.send), timeout=5)
    assert probe.status == [401]


async def test_stream_closes_listener_when_client_disconnects(
    app: FastAPI, sessions: SessionFactory
) -> None:
    probe, task = await open_stream(app)
    assert await probe.next_text(seconds=5) == ": connected\n\n"
    probe.disconnect.set()
    async with asyncio.timeout(5):
        await task
    async with sessions() as session:
        listeners = await session.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND query ILIKE 'LISTEN%'"
            )
        )
    assert listeners == 0
