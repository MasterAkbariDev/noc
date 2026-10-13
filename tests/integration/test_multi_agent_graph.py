import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select

from noc.config import Settings
from noc.db.models import (
    ActionRow,
    AgentRun,
    DiagnosisRow,
    FindingRow,
    Incident,
    IncidentEvent,
    LlmCall,
    Report,
)
from noc.db.session import SessionFactory, transaction
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.ingest import AlertIngestor
from noc.jobs import queue
from noc.llm.client import LLMClient, LLMUnavailable
from noc.llm.fake import ScriptedLLM, answer, call_tools
from noc.llm.recording import RecordingLLM
from noc.llm.types import LLMRequest, LLMResponse, Role
from noc.orchestration.graph import build_incident_graph, run_incident
from noc.orchestration.runtime import build_runtime
from noc.policy.models import AutomationLevel, Environment
from noc.store.targets import add_target, apply_inventory
from noc_sentinel.app import create_app
from noc_sentinel.nonce_store import NonceStore
from noc_shared.resources import Inventory
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import (
    DEMO_SHOP,
    KEY_ID,
    FakeSystemctl,
    prometheus_alert,
    sentinel_config,
)

pytestmark = pytest.mark.integration

STATUS_CALL = ("get_service_status", {"resource_id": DEMO_SHOP})
EXCERPT = '"active_state": "failed"'
TOOL_REF = re.compile(r'<tool_result ref="(T\d+)"')
SPECIALIST_SPANS: list[tuple[float, float]] = []


@dataclass
class MultiSkeleton:
    sessions: SessionFactory
    settings: Settings
    sentinel_http: httpx.AsyncClient
    systemctl: FakeSystemctl
    source: StaticAlertSource
    ingestor: AlertIngestor
    checkpointer: AsyncPostgresSaver

    async def open_incident(self) -> uuid.UUID:
        self.source.alerts = [prometheus_alert("ServiceDown")]
        await self.ingestor.poll_once()
        async with transaction(self.sessions) as session:
            job = await queue.claim(session, "test-worker", [INVESTIGATE_JOB], 60)
        assert job is not None
        return uuid.UUID(job.payload["incident_id"])

    async def run(self, llm: LLMClient, incident_id: uuid.UUID) -> dict[str, object]:
        runtime = build_runtime(
            self.settings, self.sessions, self.sentinel_http, RecordingLLM(llm, self.sessions)
        )
        graph = build_incident_graph(runtime, self.checkpointer)
        return await run_incident(graph, incident_id)

    async def scalar(self, statement: object) -> object:
        async with self.sessions() as session:
            return await session.scalar(statement)

    async def rows(self, statement: object) -> list[Any]:
        async with self.sessions() as session:
            return list(await session.scalars(statement))


@pytest.fixture
async def skeleton(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[MultiSkeleton]:
    config = sentinel_config(tmp_path)
    systemctl = FakeSystemctl("failed")
    app = create_app(
        config, systemctl, NonceStore(tmp_path / "nonces.sqlite3", 300), config.load_secrets()
    )
    async with transaction(sessions) as session:
        target = await add_target(
            session,
            "demo-1",
            "10.0.0.2",
            "https://demo-1:9443",
            Environment.LAB,
            KEY_ID,
            AutomationLevel.AUTO_SAFE,
        )
        target.auto_actions = ["restart_service", "start_service"]
        inventory = Inventory(
            target="demo-1",
            environment="lab",
            sentinel_version="test",
            halted=False,
            resources=config.resources,
        )
        await apply_inventory(session, target, inventory)

    settings = Settings(database_url=database_url, sentinel_key_dir=tmp_path, agent_mode="multi")
    source = StaticAlertSource()
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as sentinel_http,
        AsyncPostgresSaver.from_conn_string(settings.libpq_url) as checkpointer,
    ):
        await checkpointer.setup()
        yield MultiSkeleton(
            sessions=sessions,
            settings=settings,
            sentinel_http=sentinel_http,
            systemctl=systemctl,
            source=source,
            ingestor=AlertIngestor(source, sessions, 2),
            checkpointer=checkpointer,
        )


class RoutedLLM:
    def __init__(self, scripts: dict[str, LLMClient]) -> None:
        self._scripts = scripts

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._scripts[request.context.agent].complete(request)


class SlowFirstCall:
    def __init__(self, inner: ScriptedLLM, seconds: float) -> None:
        self._inner = inner
        self._seconds = seconds
        self._slept = False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._slept:
            self._slept = True
            started = time.perf_counter()
            await asyncio.sleep(self._seconds)
            SPECIALIST_SPANS.append((started, time.perf_counter()))
        return await self._inner.complete(request)


def specialist_payload(ref: str, finding_id: str = "F1") -> dict[str, Any]:
    return {
        "findings": [
            {
                "id": finding_id,
                "category": "service",
                "summary": "demo-shop.service is failed after being killed.",
                "severity": "critical",
                "evidence": [{"tool_call_ref": ref, "excerpt": EXCERPT}],
                "evidence_strength": "direct",
                "counter_evidence": [],
                "confidence": 0.9,
                "suspected_injection": False,
            }
        ]
    }


def cite_latest_tool_result(finding_id: str = "F1") -> Callable[[LLMRequest], LLMResponse]:
    def respond(request: LLMRequest) -> LLMResponse:
        tool_outputs = [m.content or "" for m in request.messages if m.role is Role.TOOL]
        match = TOOL_REF.search(tool_outputs[-1])
        assert match is not None
        return answer(specialist_payload(match.group(1), finding_id))

    return respond


def specialist_script(finding_id: str = "F1") -> list[Any]:
    return [
        call_tools(STATUS_CALL),
        answer("Evidence collected."),
        cite_latest_tool_result(finding_id),
    ]


def diagnosis_payload(supporting: list[str]) -> dict[str, Any]:
    return {
        "hypotheses": [
            {
                "root_cause_code": "service_crashed",
                "description": "The service process died and systemd did not restart it.",
                "confidence": 0.9,
                "supporting_findings": supporting,
                "contradicting_findings": [],
                "affected_resource_id": DEMO_SHOP,
            }
        ],
        "is_security_incident": False,
        "needs_more_info": [],
    }


async def test_service_down_fans_out_to_metrics_and_logs_then_diagnoses(
    skeleton: MultiSkeleton,
) -> None:
    incident_id = await skeleton.open_incident()
    diagnosis = ScriptedLLM([answer(diagnosis_payload(["M1", "L1"]))])
    llm = RoutedLLM(
        {
            "metrics": ScriptedLLM(specialist_script()),
            "logs": ScriptedLLM(specialist_script()),
            "diagnosis": diagnosis,
        }
    )
    await skeleton.run(llm, incident_id)

    assert await skeleton.scalar(select(Incident.status)) == "ESCALATED"
    assert await skeleton.scalar(select(Incident.root_cause_code)) == "service_crashed"

    succeeded = await skeleton.rows(select(AgentRun.agent).where(AgentRun.status == "succeeded"))
    assert sorted(succeeded) == ["diagnosis", "logs", "metrics"]

    findings = await skeleton.rows(select(FindingRow).order_by(FindingRow.label))
    assert {(row.label, row.agent) for row in findings} == {("L1", "logs"), ("M1", "metrics")}
    assert all(row.grounded for row in findings)

    planned = await skeleton.rows(
        select(IncidentEvent.payload).where(IncidentEvent.type == "investigation_planned")
    )
    assert planned[0]["specialists"] == ["metrics", "logs", "network"]
    unavailable = await skeleton.rows(
        select(IncidentEvent.payload).where(IncidentEvent.type == "specialist_unavailable")
    )
    assert unavailable == [{"specialist": "network"}]

    request = diagnosis.requests[0]
    assert request.tools == []
    user_message = request.messages[-1].content or ""
    assert '<incident_brief source="noc">' in user_message
    assert '<untrusted_data source="findings">' in user_message
    assert user_message.index("<untrusted_data") > user_message.index("<incident_brief")

    diagnoses = await skeleton.rows(select(DiagnosisRow))
    assert len(diagnoses) == 1
    assert diagnoses[0].primary_code == "service_crashed"
    assert await skeleton.scalar(select(func.count()).select_from(Report)) == 1
    actions = await skeleton.rows(select(ActionRow))
    assert all(not action.eligible for action in actions)


async def test_specialists_run_concurrently(skeleton: MultiSkeleton) -> None:
    SPECIALIST_SPANS.clear()
    incident_id = await skeleton.open_incident()
    llm = RoutedLLM(
        {
            "metrics": SlowFirstCall(ScriptedLLM(specialist_script()), 0.3),
            "logs": SlowFirstCall(ScriptedLLM(specialist_script("F1")), 0.3),
            "diagnosis": ScriptedLLM([answer(diagnosis_payload(["M1", "L1"]))]),
        }
    )
    await skeleton.run(llm, incident_id)

    assert len(SPECIALIST_SPANS) == 2
    fan_out = max(end for _, end in SPECIALIST_SPANS) - min(start for start, _ in SPECIALIST_SPANS)
    assert fan_out < 0.55
    assert await skeleton.scalar(select(Incident.status)) == "ESCALATED"


def unavailable_logs(request: LLMRequest) -> LLMResponse:
    raise LLMUnavailable("logs provider down")


async def test_failed_specialist_does_not_block_diagnosis(skeleton: MultiSkeleton) -> None:
    incident_id = await skeleton.open_incident()
    diagnosis = ScriptedLLM([answer(diagnosis_payload(["M1"]))])
    llm = RoutedLLM(
        {
            "metrics": ScriptedLLM(specialist_script()),
            "logs": ScriptedLLM([unavailable_logs]),
            "diagnosis": diagnosis,
        }
    )
    await skeleton.run(llm, incident_id)

    logs_run = await skeleton.rows(select(AgentRun).where(AgentRun.agent == "logs"))
    assert [run.status for run in logs_run] == ["failed"]
    assert (logs_run[0].error or "").startswith("LLMUnavailable")

    labels = await skeleton.rows(select(FindingRow.label))
    assert labels == ["M1"]
    failed_events = await skeleton.rows(
        select(IncidentEvent.type).where(IncidentEvent.type == "specialist_failed")
    )
    assert failed_events == ["specialist_failed"]

    assert await skeleton.scalar(select(Incident.status)) == "ESCALATED"
    assert await skeleton.scalar(select(Incident.root_cause_code)) == "service_crashed"
    assert await skeleton.scalar(select(func.count()).select_from(Report)) == 1


async def test_crash_in_diagnosis_resumes_without_rerunning_specialists(
    skeleton: MultiSkeleton,
) -> None:
    incident_id = await skeleton.open_incident()

    def crash(request: LLMRequest) -> LLMResponse:
        raise RuntimeError("worker killed")

    with pytest.raises(RuntimeError):
        await skeleton.run(
            RoutedLLM(
                {
                    "metrics": ScriptedLLM(specialist_script()),
                    "logs": ScriptedLLM(specialist_script()),
                    "diagnosis": ScriptedLLM([crash]),
                }
            ),
            incident_id,
        )
    assert await skeleton.scalar(select(Incident.status)) == "INVESTIGATING"
    specialist_runs = (
        select(func.count())
        .select_from(AgentRun)
        .where(AgentRun.agent.in_(["metrics", "logs"]), AgentRun.status == "succeeded")
    )
    assert await skeleton.scalar(specialist_runs) == 2

    await skeleton.run(
        RoutedLLM(
            {
                "metrics": ScriptedLLM([]),
                "logs": ScriptedLLM([]),
                "diagnosis": ScriptedLLM([answer(diagnosis_payload(["M1", "L1"]))]),
            }
        ),
        incident_id,
    )

    assert await skeleton.scalar(specialist_runs) == 2
    assert await skeleton.scalar(select(func.count()).select_from(FindingRow)) == 2
    assert await skeleton.scalar(select(func.count()).select_from(DiagnosisRow)) == 1
    assert await skeleton.scalar(select(func.count()).select_from(Report)) == 1
    assert await skeleton.scalar(select(Incident.status)) == "ESCALATED"
    assert await skeleton.scalar(select(func.count()).select_from(LlmCall)) >= 5
