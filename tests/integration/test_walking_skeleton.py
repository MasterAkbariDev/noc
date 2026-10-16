import re
import subprocess
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select

from noc.config import Settings
from noc.db.models import ActionRow, AgentRun, FindingRow, Incident, LlmCall, Report, ToolCall
from noc.db.session import SessionFactory, transaction
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.ingest import AlertIngestor
from noc.jobs import queue
from noc.llm.client import LLMClient
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
    KEY_ID,
    FakeSystemctl,
    investigation_payload,
    prometheus_alert,
    sentinel_config,
)

pytestmark = pytest.mark.integration

STATUS_CALL = ("get_service_status", {"resource_id": "svc:demo-shop"})


@dataclass
class Skeleton:
    sessions: SessionFactory
    settings: Settings
    sentinel_http: httpx.AsyncClient
    systemctl: FakeSystemctl
    source: StaticAlertSource
    ingestor: AlertIngestor
    checkpointer: AsyncPostgresSaver

    async def open_incident(self) -> uuid.UUID:
        self.source.alerts = [prometheus_alert()]
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


@pytest.fixture
async def skeleton(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[Skeleton]:
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

    settings = Settings(database_url=database_url, sentinel_key_dir=tmp_path)
    source = StaticAlertSource()
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as sentinel_http,
        AsyncPostgresSaver.from_conn_string(settings.libpq_url) as checkpointer,
    ):
        await checkpointer.setup()
        yield Skeleton(
            sessions=sessions,
            settings=settings,
            sentinel_http=sentinel_http,
            systemctl=systemctl,
            source=source,
            ingestor=AlertIngestor(source, sessions, 2),
            checkpointer=checkpointer,
        )


TOOL_REF = re.compile(r'<tool_result ref="(T\d+)"')


def cite_latest_tool_result(request: LLMRequest) -> LLMResponse:
    tool_outputs = [m.content or "" for m in request.messages if m.role is Role.TOOL]
    match = TOOL_REF.search(tool_outputs[-1])
    assert match is not None
    payload = investigation_payload()
    payload["findings"][0]["evidence"][0]["tool_call_ref"] = match.group(1)
    return answer(payload)


def happy_script() -> ScriptedLLM:
    return ScriptedLLM(
        [call_tools(STATUS_CALL), answer("Evidence collected."), cite_latest_tool_result]
    )


async def test_alert_to_report_without_any_mutation(skeleton: Skeleton) -> None:
    incident_id = await skeleton.open_incident()
    await skeleton.run(happy_script(), incident_id)

    incident = await skeleton.scalar(select(Incident).where(Incident.id == incident_id))
    assert isinstance(incident, Incident)
    assert incident.status == "ESCALATED"
    assert incident.escalation_reason == "no_allowed_action"
    assert incident.root_cause_code == "service_crashed"
    assert skeleton.systemctl.calls == ["demo-shop.service", "demo-shop.service"]

    tool_call = await skeleton.scalar(select(ToolCall))
    assert isinstance(tool_call, ToolCall)
    assert tool_call.ok
    assert tool_call.ref == "T1"

    finding = await skeleton.scalar(select(FindingRow))
    assert isinstance(finding, FindingRow)
    assert finding.grounded

    async with skeleton.sessions() as session:
        actions = list(await session.scalars(select(ActionRow)))
    assert {action.action_type for action in actions} == {"start_service", "restart_service"}
    assert all(not action.eligible for action in actions)
    assert all("execution_disabled" in action.gate_failures for action in actions)
    assert all(action.status == "ineligible" for action in actions)

    report = await skeleton.scalar(select(Report.markdown))
    assert isinstance(report, str)
    assert "service_crashed" in report
    assert await skeleton.scalar(select(func.count()).select_from(LlmCall)) == 3


async def test_worker_crash_mid_investigation_resumes_without_duplicates(
    skeleton: Skeleton,
) -> None:
    incident_id = await skeleton.open_incident()

    def crash(request: LLMRequest) -> LLMResponse:
        raise RuntimeError("worker killed")

    with pytest.raises(RuntimeError):
        await skeleton.run(ScriptedLLM([call_tools(STATUS_CALL), crash]), incident_id)
    assert await skeleton.scalar(select(Incident.status)) == "INVESTIGATING"

    await skeleton.run(happy_script(), incident_id)
    await skeleton.run(ScriptedLLM([]), incident_id)

    assert await skeleton.scalar(select(func.count()).select_from(Incident)) == 1
    assert await skeleton.scalar(select(func.count()).select_from(Report)) == 1
    assert await skeleton.scalar(select(func.count()).select_from(ActionRow)) == 2
    assert await skeleton.scalar(select(Incident.status)) == "ESCALATED"
    succeeded = select(func.count()).select_from(AgentRun).where(AgentRun.status == "succeeded")
    assert await skeleton.scalar(succeeded) == 1


async def test_sentinel_timeout_causes_no_duplicate_incident_and_no_mutation(
    skeleton: Skeleton,
) -> None:
    def timing_out(unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        raise subprocess.TimeoutExpired("systemctl", 5)

    skeleton.systemctl.show = timing_out
    incident_id = await skeleton.open_incident()
    unknown = investigation_payload(
        code="unknown", excerpt="TIMEOUT", confidence=0.0, resource=None
    )
    unknown["diagnosis"]["hypotheses"][0]["supporting_findings"] = []
    await skeleton.run(
        ScriptedLLM([call_tools(STATUS_CALL), answer("Tool timed out."), answer(unknown)]),
        incident_id,
    )
    await skeleton.ingestor.poll_once()

    assert await skeleton.scalar(select(func.count()).select_from(Incident)) == 1
    assert await skeleton.scalar(select(Incident.escalation_reason)) == "unknown_root_cause"
    assert await skeleton.scalar(select(func.count()).select_from(ActionRow)) == 0
    tool_call = await skeleton.scalar(select(ToolCall))
    assert isinstance(tool_call, ToolCall)
    assert not tool_call.ok
    assert "TIMEOUT" in tool_call.result_text


async def test_alerts_that_clear_before_investigation_self_resolve(skeleton: Skeleton) -> None:
    incident_id = await skeleton.open_incident()
    skeleton.source.alerts = []
    await skeleton.ingestor.poll_once()
    await skeleton.ingestor.poll_once()
    await skeleton.run(ScriptedLLM([]), incident_id)
    assert await skeleton.scalar(select(Incident.status)) == "CLOSED"
    assert await skeleton.scalar(select(func.count()).select_from(Report)) == 1
