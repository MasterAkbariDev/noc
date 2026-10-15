import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from typer.testing import CliRunner

from noc.api.app import create_app
from noc.audit.chain import verify_chain
from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.models import AuditEntry, Incident
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.policy.models import Environment
from noc.store.incidents import IncidentResolution, close_incident, transition
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOTE = "restarted by hand after the leak fix"


@pytest.fixture
async def alerts(sessions: SessionFactory) -> tuple[AlertIngestor, StaticAlertSource]:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
    source = StaticAlertSource()
    return AlertIngestor(source, sessions, missing_polls_to_resolve=2), source


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


async def open_incident(
    sessions: SessionFactory, alerts: tuple[AlertIngestor, StaticAlertSource]
) -> uuid.UUID:
    ingestor, source = alerts
    source.alerts = [prometheus_alert()]
    await ingestor.poll_once()
    async with sessions() as session:
        return (await session.scalars(select(Incident.id))).one()


async def open_escalated_incident(
    sessions: SessionFactory, alerts: tuple[AlertIngestor, StaticAlertSource]
) -> uuid.UUID:
    incident_id = await open_incident(sessions, alerts)
    async with transaction(sessions) as session:
        incident = await session.get_one(Incident, incident_id)
        await transition(session, incident, IncidentStatus.INVESTIGATING, "test")
        await transition(
            session,
            incident,
            IncidentStatus.ESCALATED,
            "test",
            EscalationReason.UNKNOWN_ROOT_CAUSE,
        )
    return incident_id


async def load_incident(sessions: SessionFactory, incident_id: uuid.UUID) -> Incident:
    async with sessions() as session:
        incident = await session.get(Incident, incident_id)
    assert incident is not None
    return incident


async def test_api_closes_escalated_incident_and_keeps_agent_root_cause(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_escalated_incident(sessions, alerts)
    response = await client.post(
        f"/api/incidents/{incident_id}/close",
        headers=AUTH,
        json={"resolution_note": NOTE, "corrected_root_cause_code": "memory_leak"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    incident = await load_incident(sessions, incident_id)
    assert incident.status == "CLOSED"
    assert incident.closed_at is not None
    assert incident.resolution_note == NOTE
    assert incident.corrected_root_cause_code == "memory_leak"
    assert incident.root_cause_code is None
    async with sessions() as session:
        actor = await session.scalar(
            select(AuditEntry.actor).where(AuditEntry.action == "incident_closed")
        )
    assert actor == "api-token"


async def test_closing_a_new_incident_is_a_conflict(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    response = await client.post(
        f"/api/incidents/{incident_id}/close", headers=AUTH, json={"resolution_note": NOTE}
    )
    assert response.status_code == 409
    assert (await load_incident(sessions, incident_id)).status == "NEW"


@pytest.mark.parametrize(
    "payload",
    [
        {"resolution_note": NOTE, "corrected_root_cause_code": "not_a_code"},
        {"resolution_note": ""},
        {"resolution_note": "x" * 2001},
    ],
)
async def test_invalid_resolution_is_rejected_and_nothing_changes(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
    payload: dict[str, str],
) -> None:
    incident_id = await open_escalated_incident(sessions, alerts)
    response = await client.post(f"/api/incidents/{incident_id}/close", headers=AUTH, json=payload)
    assert response.status_code == 422
    assert (await load_incident(sessions, incident_id)).status == "ESCALATED"


async def test_unknown_incident_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"/api/incidents/{uuid.uuid4()}/close", headers=AUTH, json={"resolution_note": NOTE}
    )
    assert response.status_code == 404


async def test_close_endpoint_requires_token(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_escalated_incident(sessions, alerts)
    response = await client.post(
        f"/api/incidents/{incident_id}/close", json={"resolution_note": NOTE}
    )
    assert response.status_code == 401
    assert (await load_incident(sessions, incident_id)).status == "ESCALATED"


async def test_close_writes_audit_entry_and_chain_stays_intact(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
) -> None:
    incident_id = await open_escalated_incident(sessions, alerts)
    async with transaction(sessions) as session:
        await close_incident(session, incident_id, IncidentResolution(resolution_note=NOTE), "cli")
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEntry)) == 1
        assert await verify_chain(session) is None


async def test_alert_after_close_opens_a_new_incident(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
) -> None:
    ingestor, source = alerts
    incident_id = await open_escalated_incident(sessions, alerts)
    async with transaction(sessions) as session:
        await close_incident(session, incident_id, IncidentResolution(resolution_note=NOTE), "api")
    source.alerts = []
    await ingestor.poll_once()
    await ingestor.poll_once()
    source.alerts = [prometheus_alert()]
    await ingestor.poll_once()
    async with sessions() as session:
        statuses = set((await session.scalars(select(Incident.status))).all())
        count = await session.scalar(select(func.count()).select_from(Incident))
    assert count == 2
    assert statuses == {"CLOSED", "NEW"}


async def test_an_alert_only_kept_firing_after_close_opens_no_duplicate(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
) -> None:
    ingestor, source = alerts
    incident_id = await open_escalated_incident(sessions, alerts)
    async with transaction(sessions) as session:
        await close_incident(session, incident_id, IncidentResolution(resolution_note=NOTE), "api")
    source.alerts = [prometheus_alert(keep_firing_since=datetime(2026, 10, 13, 9, 5, tzinfo=UTC))]
    await ingestor.poll_once()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Incident)) == 1
    source.alerts = [prometheus_alert()]
    await ingestor.poll_once()
    async with sessions() as session:
        statuses = set((await session.scalars(select(Incident.status))).all())
    assert statuses == {"CLOSED", "NEW"}


async def test_cli_close_then_second_close_is_rejected(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = await open_escalated_incident(sessions, alerts)
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: Settings(database_url=database_url))
    runner = CliRunner()
    command = ["incidents", "close", str(incident_id), "--note", NOTE]
    first = await asyncio.to_thread(
        runner.invoke, cli_app, [*command, "--root-cause", "memory_leak"]
    )
    assert first.exit_code == 0, first.output
    assert "status=CLOSED" in first.output
    second = await asyncio.to_thread(runner.invoke, cli_app, command)
    assert second.exit_code == 2
    incident = await load_incident(sessions, incident_id)
    assert incident.corrected_root_cause_code == "memory_leak"
