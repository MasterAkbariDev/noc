import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.config import Settings
from noc.db.models import AgentRun, Incident, LlmCall, ToolCall
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import DEMO_SHOP, KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
RAW_OUTPUT = "RAW-SYSTEMCTL-OUTPUT-MUST-NOT-LEAK"
START = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


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


async def seed_trace(sessions: SessionFactory, incident_id: uuid.UUID) -> None:
    async with transaction(sessions) as session:
        session.add_all(
            [
                AgentRun(
                    incident_id=incident_id,
                    agent="investigator",
                    status="done",
                    started_at=START + timedelta(seconds=20),
                    ended_at=START + timedelta(seconds=50),
                    rounds=2,
                    llm_calls=1,
                    tool_calls=2,
                ),
                AgentRun(
                    incident_id=incident_id,
                    agent="detector",
                    status="done",
                    started_at=START,
                    ended_at=START + timedelta(seconds=10),
                    rounds=0,
                    llm_calls=0,
                    tool_calls=0,
                ),
                tool_call(incident_id, "T2", START + timedelta(seconds=30)),
                tool_call(incident_id, "T1", START + timedelta(seconds=25)),
                LlmCall(
                    incident_id=incident_id,
                    agent="investigator",
                    tier="strong",
                    provider="gemini",
                    model="gemini-2.5-flash",
                    mode="json",
                    request_hash="0" * 64,
                    tokens_in=900,
                    tokens_out=120,
                    latency_ms=800,
                    wait_ms=0,
                    finish_reason="stop",
                    created_at=START + timedelta(seconds=40),
                ),
                LlmCall(
                    incident_id=incident_id,
                    agent="investigator",
                    tier="fast",
                    provider="groq",
                    model="llama",
                    mode="json",
                    request_hash="1" * 64,
                    tokens_in=300,
                    tokens_out=40,
                    latency_ms=200,
                    wait_ms=0,
                    finish_reason="stop",
                    created_at=START + timedelta(seconds=22),
                ),
            ]
        )


def tool_call(incident_id: uuid.UUID, ref: str, started_at: datetime) -> ToolCall:
    return ToolCall(
        ref=ref,
        incident_id=incident_id,
        agent="investigator",
        tool="get_service_status",
        args={"resource_id": DEMO_SHOP},
        permission="read",
        decision="allow",
        decision_reason=None,
        ok=True,
        started_at=started_at,
        duration_ms=12,
        result={"raw": RAW_OUTPUT},
        result_text=RAW_OUTPUT,
        result_sha256="2" * 64,
        truncated=False,
        injection_flags=[],
    )


async def test_trace_requires_token(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    response = await client.get(f"/api/incidents/{incident_id}/trace")
    assert response.status_code == 401


async def test_unknown_incident_trace_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/incidents/{uuid.uuid4()}/trace", headers=AUTH)
    assert response.status_code == 404


async def test_trace_lists_runs_tool_calls_and_llm_calls_in_start_order(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await seed_trace(sessions, incident_id)
    response = await client.get(f"/api/incidents/{incident_id}/trace", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert [run["agent"] for run in body["agent_runs"]] == ["detector", "investigator"]
    assert [call["ref"] for call in body["tool_calls"]] == ["T1", "T2"]
    assert [call["tokens_in"] for call in body["llm_calls"]] == [300, 900]
    assert body["tool_calls"][0]["args"] == {"resource_id": DEMO_SHOP}
    assert body["agent_runs"][1]["tool_calls"] == 2


async def test_trace_never_exposes_result_text_or_request_hashes(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await seed_trace(sessions, incident_id)
    response = await client.get(f"/api/incidents/{incident_id}/trace", headers=AUTH)
    assert RAW_OUTPUT not in response.text
    assert "result_text" not in response.text
    assert "request_hash" not in response.text
    assert "result_sha256" not in response.text
    assert '"result"' not in response.text
    assert '"raw"' not in response.text
