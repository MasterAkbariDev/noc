import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.config import Settings
from noc.db.models import ActionRow, DiagnosisRow, FindingRow, Incident
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.policy.models import Environment
from noc.store.incidents import transition
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TITLE = "ServiceDown on demo-1/svc:demo-shop"
RESTART = "restart_service"


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


async def walk(
    sessions: SessionFactory,
    incident_id: uuid.UUID,
    path: list[IncidentStatus],
    reason: EscalationReason | None = None,
) -> None:
    async with transaction(sessions) as session:
        incident = await session.get_one(Incident, incident_id)
        for index, status in enumerate(path):
            is_last = index == len(path) - 1
            await transition(session, incident, status, "test", reason if is_last else None)


def finding_row(incident_id: uuid.UUID, label: str, **overrides: Any) -> FindingRow:
    values: dict[str, Any] = {
        "incident_id": incident_id,
        "agent": "metrics",
        "label": label,
        "category": "service",
        "severity": "critical",
        "summary": f"finding {label}",
        "evidence": [{"tool_call_ref": "T1", "excerpt": "active_state"}],
        "evidence_strength": "direct",
        "counter_evidence": [],
        "confidence": 0.8,
        "suspected_injection": False,
        "grounded": True,
    }
    return FindingRow(**(values | overrides))


def diagnosis_row(
    incident_id: uuid.UUID, primary: str, confidence: float, supporting: list[str]
) -> DiagnosisRow:
    return DiagnosisRow(
        incident_id=incident_id,
        primary_code=primary,
        confidence=confidence,
        is_security_incident=False,
        hypotheses=[
            {
                "root_cause_code": primary,
                "description": f"{primary} is likely",
                "confidence": confidence,
                "supporting_findings": supporting,
                "contradicting_findings": [],
                "affected_resource_id": "svc:demo-shop",
            },
            {
                "root_cause_code": "memory_leak",
                "description": "memory leak is possible",
                "confidence": 0.1,
                "supporting_findings": [],
                "contradicting_findings": [],
                "affected_resource_id": None,
            },
        ],
        needs_more_info=[],
        ungrounded_findings=0,
    )


async def add_rows(sessions: SessionFactory, *rows: Any) -> None:
    async with transaction(sessions) as session:
        session.add_all(rows)


async def add_action(
    sessions: SessionFactory, incident_id: uuid.UUID, status: str, eligible: bool, gates: list[str]
) -> None:
    async with transaction(sessions) as session:
        incident = await session.get_one(Incident, incident_id)
        session.add(
            ActionRow(
                incident_id=incident.id,
                target_id=incident.target_id,
                action_type=RESTART,
                resource_id="svc:demo-shop",
                params={},
                status=status,
                permission_class="SAFE_ACTION",
                eligible=eligible,
                auto_executable=False,
                gate_failures=gates,
                reasons=[],
                impact_score=3,
                high_impact=False,
                policy_version="test",
                action_hash=uuid.uuid4().hex,
            )
        )


async def story(client: httpx.AsyncClient, incident_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(f"/api/incidents/{incident_id}/story", headers=AUTH)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def step_states(body: dict[str, Any]) -> dict[str, str]:
    return {step["key"]: step["state"] for step in body["steps"]}


async def test_escalated_story_explains_the_blocked_action(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(
        sessions,
        incident_id,
        [IncidentStatus.INVESTIGATING, IncidentStatus.DIAGNOSED, IncidentStatus.ESCALATED],
        EscalationReason.EXECUTION_NOT_AVAILABLE,
    )
    await add_rows(
        sessions,
        finding_row(incident_id, "F1", summary="demo-shop.service is failed."),
        diagnosis_row(incident_id, "service_crashed", 0.9, ["F1"]),
    )
    await add_action(sessions, incident_id, "ineligible", False, ["execution_disabled"])
    body = await story(client, incident_id)
    assert body["status"] == "ESCALATED"
    assert body["status_label"] == "Needs you"
    assert body["headline"] == (
        f"{TITLE} needs you: automatic actions are switched off on this server."
    )
    assert step_states(body) == {
        "detected": "done",
        "investigated": "done",
        "diagnosed": "done",
        "decided": "done",
        "acted": "skipped",
        "outcome": "current",
    }
    assert body["what_we_did"]["text"] == (
        "Nothing — automatic actions are switched off on this server."
    )
    considered = body["what_we_did"]["considered"]
    assert considered[0]["verdict"] == "blocked"
    assert considered[0]["verdict_label"] == "Blocked"
    assert considered[0]["reasons"] == ["automatic actions are switched off on this server"]
    assert considered[0]["technical"] == ["execution_disabled"]
    advice = body["what_you_should_do"]
    assert advice["text"] == "Fix it by hand, then close the incident with a note."
    assert advice["steps"][0] == {
        "text": "See whether the service is stopped, failed or restarting.",
        "command": "systemctl status <service>",
    }
    assert {"text": "Start it again.", "command": "sudo systemctl start <service>"} in advice[
        "steps"
    ]
    assert body["what_we_found"]["root_cause_label"] == "The service crashed and did not restart"
    assert body["what_we_found"]["text"] == (
        "Root cause: The service crashed and did not restart (90% confidence)."
    )


async def test_resolved_story_shows_every_step_done(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(
        sessions,
        incident_id,
        [
            IncidentStatus.INVESTIGATING,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.PLANNED,
            IncidentStatus.REMEDIATING,
            IncidentStatus.VERIFYING,
            IncidentStatus.RESOLVED,
        ],
    )
    await add_rows(sessions, diagnosis_row(incident_id, "service_crashed", 0.9, []))
    await add_action(sessions, incident_id, "succeeded", True, [])
    body = await story(client, incident_id)
    assert body["status_label"] == "Resolved"
    assert set(step_states(body).values()) == {"done"}
    assert body["steps"][-1]["label"] == "Resolved"
    assert body["steps"][-1]["at"] is not None
    assert body["what_we_did"]["text"] == "Ran restart service."
    assert body["what_we_did"]["considered"][0]["verdict"] == "ran"
    advice = body["what_you_should_do"]
    assert advice["text"] == "Nothing. This incident is finished."
    assert advice["steps"][0]["text"].startswith("If it stopped on its own")


async def test_investigating_story_has_one_current_step_and_pending_rest(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(sessions, incident_id, [IncidentStatus.INVESTIGATING])
    body = await story(client, incident_id)
    assert body["headline"] == f"{TITLE}: investigating. The NOC is working on it."
    assert step_states(body) == {
        "detected": "done",
        "investigated": "current",
        "diagnosed": "pending",
        "decided": "pending",
        "acted": "pending",
        "outcome": "pending",
    }
    assert body["steps"][-1]["label"] == "Outcome"
    assert body["what_we_found"] == {
        "text": "Not diagnosed yet.",
        "root_cause_code": None,
        "root_cause_label": None,
        "confidence": None,
        "points": [],
    }
    assert body["what_we_did"]["text"] == "No action was proposed."
    assert body["what_you_should_do"]["text"] == "Nothing yet — the agents are still working."


async def test_self_resolved_story_skips_the_steps_that_never_ran(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(sessions, incident_id, [IncidentStatus.INVESTIGATING, IncidentStatus.SELF_RESOLVED])
    body = await story(client, incident_id)
    assert step_states(body) == {
        "detected": "done",
        "investigated": "done",
        "diagnosed": "skipped",
        "decided": "skipped",
        "acted": "skipped",
        "outcome": "done",
    }
    assert body["steps"][-1]["label"] == "Resolved on its own"
    assert body["what_you_should_do"]["text"] == "Nothing. This incident is finished."


async def test_investigation_that_escalated_without_a_diagnosis_marks_the_step_failed(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(
        sessions,
        incident_id,
        [IncidentStatus.INVESTIGATING, IncidentStatus.ESCALATED],
        EscalationReason.INVESTIGATION_FAILED,
    )
    body = await story(client, incident_id)
    assert step_states(body)["investigated"] == "failed"
    assert step_states(body)["outcome"] == "current"
    assert body["what_we_found"]["text"] == "Not diagnosed yet."
    assert body["what_we_did"]["text"] == "Nothing — the investigation stopped before it finished."
    advice = body["what_you_should_do"]
    assert advice["text"] == "Investigate by hand, then close the incident with a note."
    assert advice["steps"][0]["command"] == "systemctl status <service>"


async def test_story_cites_the_alert_and_ranks_supporting_findings_first(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(sessions, incident_id, [IncidentStatus.INVESTIGATING])
    await add_rows(
        sessions,
        diagnosis_row(incident_id, "service_crashed", 0.9, ["F2"]),
        finding_row(incident_id, "F1", confidence=0.95, summary="first finding"),
        finding_row(incident_id, "F2", confidence=0.6, summary="supporting finding"),
        finding_row(incident_id, "F3", confidence=0.99, grounded=False),
        finding_row(incident_id, "F4", confidence=0.2),
        finding_row(incident_id, "F5", confidence=0.1),
    )
    body = await story(client, incident_id)
    what_happened = body["what_happened"]
    assert what_happened["text"].startswith("svc:demo-shop is not active at ")
    assert what_happened["text"].endswith(" UTC.")
    assert what_happened["technical"] == (
        "alertname=ServiceDown, resource=svc:demo-shop, severity=critical, target=demo-1"
    )
    points = body["what_we_found"]["points"]
    assert [point["label"] for point in points] == ["F2", "F1", "F4", "F5"]
    assert points[0] == {
        "text": "supporting finding",
        "agent": "metrics",
        "label": "F2",
        "evidence": [{"source": "a check on the server", "quote": "active_state"}],
        "grounded": True,
    }


async def test_story_waiting_for_approval_asks_for_a_decision(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(
        sessions,
        incident_id,
        [
            IncidentStatus.INVESTIGATING,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.PLANNED,
            IncidentStatus.AWAITING_APPROVAL,
        ],
    )
    await add_rows(sessions, diagnosis_row(incident_id, "service_crashed", 0.9, []))
    await add_action(sessions, incident_id, "pending_approval", True, [])
    body = await story(client, incident_id)
    assert body["headline"] == (
        f"{TITLE} needs you: a planned action is waiting for your approval."
    )
    assert body["what_you_should_do"] == {
        "text": "Review the planned action below and approve or reject it.",
        "steps": [
            {"text": "Check the gates and the impact score.", "command": None},
            {
                "text": "Approve to let the NOC run it, or reject to handle it yourself.",
                "command": None,
            },
        ],
    }
    assert body["what_we_did"]["considered"][0]["verdict"] == "approval"
    assert body["what_we_did"]["considered"][0]["verdict_label"] == "Waiting for approval"


async def test_a_failed_action_is_described_as_tried_and_failed(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    await walk(
        sessions,
        incident_id,
        [
            IncidentStatus.INVESTIGATING,
            IncidentStatus.DIAGNOSED,
            IncidentStatus.PLANNED,
            IncidentStatus.REMEDIATING,
        ],
    )
    await add_rows(sessions, diagnosis_row(incident_id, "service_crashed", 0.9, []))
    await add_action(sessions, incident_id, "failed", True, [])
    body = await story(client, incident_id)
    assert body["what_we_did"]["text"] == "Tried restart service, and it failed."
    assert body["what_we_did"]["considered"][0]["verdict"] == "failed"
    assert body["what_we_did"]["considered"][0]["verdict_label"] == "Failed"


async def test_story_of_unknown_incident_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/incidents/{uuid.uuid4()}/story", headers=AUTH)
    assert response.status_code == 404


async def test_story_requires_the_token(
    sessions: SessionFactory,
    alerts: tuple[AlertIngestor, StaticAlertSource],
    client: httpx.AsyncClient,
) -> None:
    incident_id = await open_incident(sessions, alerts)
    response = await client.get(f"/api/incidents/{incident_id}/story")
    assert response.status_code == 401
