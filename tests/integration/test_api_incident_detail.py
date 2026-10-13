import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.config import Settings
from noc.db.models import DiagnosisRow, FindingRow, Incident
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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


def finding_row(incident_id: uuid.UUID, label: str) -> FindingRow:
    return FindingRow(
        incident_id=incident_id,
        agent="metrics",
        label=label,
        category="saturation",
        severity="high",
        summary=f"finding {label}",
        evidence=[{"ref": label}],
        evidence_strength="strong",
        counter_evidence=["C1"],
        confidence=0.8,
        suspected_injection=False,
        grounded=True,
    )


def hypothesis(code: str, supporting: list[str], contradicting: list[str]) -> dict[str, Any]:
    return {
        "root_cause_code": code,
        "description": f"{code} is likely",
        "confidence": 0.7,
        "supporting_findings": supporting,
        "contradicting_findings": contradicting,
        "affected_resource_id": "demo-shop",
    }


async def test_detail_includes_diagnosis_with_hypotheses_and_finding_fields(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    async with transaction(sessions) as session:
        session.add(finding_row(incident_id, "M1"))
        session.add(
            DiagnosisRow(
                incident_id=incident_id,
                primary_code="memory_leak",
                confidence=0.75,
                is_security_incident=False,
                hypotheses=[
                    hypothesis("memory_leak", ["M1"], ["L1"]),
                    hypothesis("disk_full", [], ["M1"]),
                ],
                needs_more_info=["heap dump"],
                ungrounded_findings=2,
            )
        )
    response = await client.get(f"/api/incidents/{incident_id}", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "demo-1"
    assert body["mode"] == "single"
    assert body["diagnosed_at"] is None
    assert body["diagnosis"]["primary_code"] == "memory_leak"
    assert body["diagnosis"]["ungrounded_findings"] == 2
    assert body["diagnosis"]["needs_more_info"] == ["heap dump"]
    first, second = body["diagnosis"]["hypotheses"]
    assert first["supporting_findings"] == ["M1"]
    assert first["contradicting_findings"] == ["L1"]
    assert second["contradicting_findings"] == ["M1"]
    finding = body["findings"][0]
    assert finding["evidence_strength"] == "strong"
    assert finding["counter_evidence"] == ["C1"]
    assert finding["grounded"] is True


async def test_detail_diagnosis_is_null_when_none_exists(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    response = await client.get(f"/api/incidents/{incident_id}", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["diagnosis"] is None


async def test_list_includes_target_name(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    await open_incident(sessions, alerts)
    response = await client.get("/api/incidents", headers=AUTH)
    assert response.status_code == 200
    assert [item["target"] for item in response.json()] == ["demo-1"]
