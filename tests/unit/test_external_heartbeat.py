from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from noc.config import Settings
from noc.db.base import utc_now
from noc.db.session import SessionFactory
from noc.detection.ingest import AlertIngestor
from noc.doctor import check_external_heartbeat
from noc.orchestration.graph import IncidentGraph
from noc.worker import main as worker_main
from noc.worker.heartbeat import PollStatus, polling_is_fresh
from noc.worker.main import Worker

URL = "https://hc.example/ping/abc"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.queries = 0

    async def execute(self, statement: object) -> None:
        self.queries += 1


def fake_sessions(session: FakeSession) -> SessionFactory:
    @asynccontextmanager
    async def factory() -> AsyncIterator[FakeSession]:
        yield session

    return cast(SessionFactory, factory)


def worker_with(session: FakeSession) -> Worker:
    return Worker(
        Settings(poll_interval_seconds=10, external_heartbeat_url=SecretStr(URL)),
        sessions=fake_sessions(session),
        graph=cast(IncidentGraph, None),
        ingestor=cast(AlertIngestor, None),
    )


def answering(status: int, seen: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(status)

    real_client = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(worker_main.httpx, "AsyncClient", client)


def test_polling_is_fresh_only_after_a_recent_success() -> None:
    window = timedelta(seconds=30)
    assert not polling_is_fresh(PollStatus(), NOW, window)
    assert polling_is_fresh(PollStatus(last_ok_at=NOW - timedelta(seconds=29)), NOW, window)
    assert not polling_is_fresh(PollStatus(last_ok_at=NOW - timedelta(seconds=31)), NOW, window)


async def test_a_healthy_worker_pings_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    answering(200, seen, monkeypatch)
    session = FakeSession()
    worker = worker_with(session)
    worker._poll.ok(utc_now())
    assert await worker.ping_external_once(URL) is True
    assert seen == [URL]
    assert session.queries == 1


async def test_stale_alert_polling_means_no_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    answering(200, seen, monkeypatch)
    session = FakeSession()
    worker = worker_with(session)
    worker._poll.ok(utc_now() - timedelta(minutes=5))
    assert await worker.ping_external_once(URL) is False
    assert seen == []
    assert session.queries == 0


async def test_a_refused_ping_is_reported_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    answering(503, seen, monkeypatch)
    worker = worker_with(FakeSession())
    worker._poll.ok(utc_now())
    assert await worker.ping_external_once(URL) is False


def test_doctor_warns_until_a_heartbeat_url_is_set() -> None:
    assert check_external_heartbeat(Settings(_env_file=None)).status == "warn"
    configured = Settings(_env_file=None, external_heartbeat_url=SecretStr(URL))
    result = check_external_heartbeat(configured)
    assert result.status == "ok"
    assert URL not in result.detail
