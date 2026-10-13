import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.api.system import migration_revision
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Incident, IncidentEvent, Job, WorkerHeartbeat
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.ingest import AlertIngestor
from noc.orchestration.graph import IncidentGraph
from noc.policy.models import Environment
from noc.store.targets import add_target
from noc.worker.main import Worker
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "health-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
HEALTH_PATH = "/api/system/health"
COMPONENT_ORDER = [
    "worker",
    "alert_polling",
    "prometheus",
    "egress",
    "database",
    "version",
    "updater",
]
PROXY_VARIABLES = ("NOC_GEMINI_PROXY", "NOC_GROQ_PROXY")


@pytest.fixture(autouse=True)
def no_egress_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def all_targets_up(request: httpx.Request) -> httpx.Response:
    body = {
        "status": "success",
        "data": {
            "activeTargets": [{"labels": {"job": "node"}, "health": "up"}],
            "droppedTargets": [],
        },
    }
    return httpx.Response(200, json=body)


def prometheus_unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def make_settings(**overrides: Any) -> Settings:
    return Settings(api_token=SecretStr(TOKEN), _env_file=None, **overrides)


@asynccontextmanager
async def api_client(
    sessions: SessionFactory,
    settings: Settings,
    prometheus: Any = None,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    handler = prometheus or all_targets_up
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as prometheus_http:
        app.state.prometheus = PrometheusReader(prometheus_http, settings.prometheus_url)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://noc"
        ) as client:
            yield client


async def fetch_health(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(HEALTH_PATH, headers=AUTH)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def component(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in body["components"] if item["key"] == key)


class ReportingIngestor:
    def __init__(self, outcome: bool | Exception) -> None:
        self.outcome = outcome
        self.worker: Worker | None = None

    async def poll_once(self) -> bool:
        if self.worker is not None:
            self.worker.stop()
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_worker(sessions: SessionFactory, settings: Settings, ingestor: Any) -> Worker:
    return Worker(settings, sessions, cast(IncidentGraph, None), cast(AlertIngestor, ingestor))


async def test_health_requires_the_token(sessions: SessionFactory) -> None:
    async with api_client(sessions, make_settings()) as client:
        response = await client.get(HEALTH_PATH)
    assert response.status_code == 401


async def test_health_lists_every_component_in_order(sessions: SessionFactory) -> None:
    async with api_client(sessions, make_settings()) as client:
        body = await fetch_health(client)
    assert [item["key"] for item in body["components"]] == COMPONENT_ORDER


async def test_a_worker_that_never_reported_makes_the_verdict_down(
    sessions: SessionFactory,
) -> None:
    async with api_client(sessions, make_settings()) as client:
        body = await fetch_health(client)
    assert component(body, "worker")["status"] == "down"
    assert body["verdict"] == "down"


async def test_a_beating_worker_is_ok_and_the_rest_decides_the_verdict(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    settings = make_settings(version="main", git_sha="0123456789abcdef")
    ingestor = ReportingIngestor(True)
    worker = make_worker(sessions, settings, ingestor)
    ingestor.worker = worker
    await worker.run_ingest_loop()
    await worker.beat_once()
    async with api_client(sessions, settings) as client:
        body = await fetch_health(client)
    worker_health = component(body, "worker")
    assert worker_health["status"] == "ok"
    assert worker_health["details"] == {"version": "main"}
    assert component(body, "version")["summary"] == "NOC main (0123456789ab)"
    assert component(body, "prometheus")["status"] == "ok"
    assert component(body, "egress")["status"] == "unknown"
    assert component(body, "database")["status"] == "ok"
    assert component(body, "updater")["status"] == "unknown"
    assert body["verdict"] == "ok"


async def test_repeated_beats_keep_one_row_per_worker(sessions: SessionFactory) -> None:
    worker = make_worker(sessions, make_settings(), ReportingIngestor(True))
    await worker.beat_once()
    await worker.beat_once()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(WorkerHeartbeat)) == 1


async def test_a_worker_with_an_old_heartbeat_is_down(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        session.add(
            WorkerHeartbeat(
                worker_id="old-host:1",
                started_at=utc_now() - timedelta(days=1),
                last_beat_at=utc_now() - timedelta(hours=1),
                version="main",
            )
        )
    async with api_client(sessions, make_settings()) as client:
        body = await fetch_health(client)
    assert component(body, "worker")["status"] == "down"
    assert body["verdict"] == "down"


async def test_a_failed_poll_is_reported_by_the_worker(sessions: SessionFactory) -> None:
    settings = make_settings()
    ingestor = ReportingIngestor(False)
    worker = make_worker(sessions, settings, ingestor)
    ingestor.worker = worker
    await worker.run_ingest_loop()
    await worker.beat_once()
    async with api_client(sessions, settings) as client:
        polling = component(await fetch_health(client), "alert_polling")
    assert polling["status"] == "degraded"
    assert "last error: Prometheus did not answer the alert poll" in polling["summary"]


async def test_a_raising_poll_records_the_exception_type(sessions: SessionFactory) -> None:
    settings = make_settings()
    ingestor = ReportingIngestor(RuntimeError("database went away"))
    worker = make_worker(sessions, settings, ingestor)
    ingestor.worker = worker
    await worker.run_ingest_loop()
    await worker.beat_once()
    async with api_client(sessions, settings) as client:
        polling = component(await fetch_health(client), "alert_polling")
    assert polling["summary"].endswith("last error: RuntimeError")


async def test_a_down_prometheus_makes_the_verdict_degraded(sessions: SessionFactory) -> None:
    settings = make_settings()
    await make_worker(sessions, settings, ReportingIngestor(True)).beat_once()
    async with api_client(sessions, settings, prometheus_unreachable) as client:
        body = await fetch_health(client)
    assert component(body, "prometheus")["status"] == "down"
    assert body["verdict"] == "degraded"


async def test_a_rolled_back_update_degrades_the_verdict(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    status_file = tmp_path / "status.json"
    status_file.write_text(
        json.dumps(
            {
                "ts": "2026-10-13T11:55:00+00:00",
                "result": "rolled_back",
                "image": "ghcr.io/example/noc:main",
                "message": "rolled back to 1a2b3c4d5e6f",
            }
        ),
        encoding="utf-8",
    )
    settings = make_settings(update_status_file=status_file)
    await make_worker(sessions, settings, ReportingIngestor(True)).beat_once()
    async with api_client(sessions, settings) as client:
        updater = component(await fetch_health(client), "updater")
    assert updater["status"] == "degraded"
    assert updater["details"]["result"] == "rolled_back"


async def test_an_incident_that_stopped_moving_is_listed_with_its_job(
    sessions: SessionFactory,
) -> None:
    now = utc_now()
    async with transaction(sessions) as session:
        target = await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        stuck = Incident(
            target_id=target.id,
            status="INVESTIGATING",
            severity="critical",
            title="ServiceDown on demo-1",
            trace_id="a" * 32,
            opened_at=now - timedelta(minutes=40),
        )
        session.add(stuck)
        await session.flush()
        session.add(
            IncidentEvent(
                incident_id=stuck.id,
                ts=now - timedelta(minutes=20),
                type="investigation_started",
                actor="worker",
                payload={},
            )
        )
        session.add(
            Job(
                kind="investigate",
                payload={"incident_id": str(stuck.id)},
                status="dead",
                attempts=5,
                last_error="LLMError: provider said 400",
            )
        )
        stuck_id = stuck.id
        other = await add_target(
            session, "demo-2", "10.0.0.3", "https://demo-2:9443", Environment.LAB, KEY_ID
        )
        session.add(
            Incident(
                target_id=other.id,
                status="INVESTIGATING",
                severity="critical",
                title="ServiceDown on demo-2",
                trace_id="b" * 32,
                opened_at=now - timedelta(minutes=2),
            )
        )
    async with api_client(sessions, make_settings()) as client:
        body = await fetch_health(client)
    assert len(body["stuck_incidents"]) == 1
    row = body["stuck_incidents"][0]
    assert row["id"] == str(stuck_id)
    assert row["target"] == "demo-1"
    assert row["status"] == "INVESTIGATING"
    assert row["job_status"] == "dead"
    assert row["job_attempts"] == 5
    assert row["job_last_error"] == "LLMError: provider said 400"
    since = datetime.fromisoformat(row["since"])
    assert abs(since - (now - timedelta(minutes=20))) < timedelta(minutes=1)


async def test_the_migration_revision_comes_from_alembic_version(
    sessions: SessionFactory,
) -> None:
    async with sessions() as session:
        assert await migration_revision(session) is None
        await session.execute(
            text("CREATE TEMP TABLE alembic_version (version_num varchar(32) NOT NULL)")
        )
        await session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0007')"))
        assert await migration_revision(session) == "0007"


async def test_an_unreachable_database_is_reported_instead_of_raised() -> None:
    engine = create_engine("postgresql+psycopg://noc:noc@127.0.0.1:1/noc")
    try:
        async with api_client(create_session_factory(engine), make_settings()) as client:
            body = await fetch_health(client)
    finally:
        await engine.dispose()
    assert component(body, "database")["status"] == "down"
    assert component(body, "worker")["status"] == "unknown"
    assert body["stuck_incidents"] == []
    assert body["verdict"] == "down"
