import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import SecretStr
from sqlalchemy import func, select, update

from noc.api.app import create_app as create_api
from noc.config import Settings
from noc.db.models import (
    ActionRow,
    Approval,
    Incident,
    IncidentEvent,
    Job,
    Report,
    Target,
    ToolCall,
)
from noc.db.session import SessionFactory, transaction
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.ingest import AlertIngestor
from noc.jobs import queue
from noc.llm.recording import RecordingLLM
from noc.orchestration.graph import (
    build_incident_graph,
    build_remediation_graph,
    run_incident,
)
from noc.orchestration.runtime import Runtime, build_runtime
from noc.policy.models import AutomationLevel, Environment
from noc.store.remediation import REMEDIATE_JOB, ApprovalConflict, record_approval
from noc.store.targets import add_target, apply_inventory
from noc_sentinel.app import create_app
from noc_sentinel.config import ActionsConfig
from noc_sentinel.nonce_store import NonceStore
from noc_shared.resources import Inventory
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.integration.test_walking_skeleton import happy_script
from tests.support.builders import KEY_ID, FakeSystemctl, prometheus_alert, sentinel_config

pytestmark = pytest.mark.integration

API_TOKEN = "test-token"
API_AUTH = {"Authorization": f"Bearer {API_TOKEN}"}
START_ARGV = ("/usr/bin/systemctl", "start", "demo-shop.service")
RESTART_ARGV = ("/usr/bin/systemctl", "restart", "demo-shop.service")


class FakeActionRunner:
    def __init__(self, systemctl: FakeSystemctl, returncode: int = 0) -> None:
        self.systemctl = systemctl
        self.returncode = returncode
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        self.calls.append(argv)
        if self.returncode == 0:
            self.systemctl.active_state = "active"
        return self.returncode


@dataclass
class Lab:
    sessions: SessionFactory
    settings: Settings
    runtime: Runtime
    sentinel_http: httpx.AsyncClient
    systemctl: FakeSystemctl
    runner: FakeActionRunner
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

    async def investigate(self, incident_id: uuid.UUID) -> None:
        runtime = build_runtime(
            self.settings,
            self.sessions,
            self.sentinel_http,
            RecordingLLM(happy_script(), self.sessions),
        )
        await run_incident(build_incident_graph(runtime, self.checkpointer), incident_id)

    async def remediate(self, incident_id: uuid.UUID, action_id: uuid.UUID) -> None:
        graph = build_remediation_graph(self.runtime, self.checkpointer)
        await run_incident(graph, incident_id, str(action_id))

    async def clear_alerts_once_verifying(self, incident_id: uuid.UUID) -> None:
        for _ in range(1000):
            if await self.status(incident_id) in ("VERIFYING", "RESOLVED", "ESCALATED"):
                break
            await asyncio.sleep(0.02)
        self.source.alerts = []
        await self.ingestor.poll_once()
        await self.ingestor.poll_once()

    async def status(self, incident_id: uuid.UUID) -> str:
        async with self.sessions() as session:
            incident = await session.get_one(Incident, incident_id)
            return incident.status

    async def incident(self, incident_id: uuid.UUID) -> Incident:
        async with self.sessions() as session:
            return await session.get_one(Incident, incident_id)

    async def chosen_action(self, incident_id: uuid.UUID) -> ActionRow:
        async with self.sessions() as session:
            action = await session.scalar(
                select(ActionRow).where(
                    ActionRow.incident_id == incident_id,
                    ActionRow.status.not_in(("proposed", "ineligible")),
                )
            )
        assert action is not None
        return action

    async def event_types(self, incident_id: uuid.UUID) -> list[str]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(IncidentEvent.type)
                .where(IncidentEvent.incident_id == incident_id)
                .order_by(IncidentEvent.id)
            )
            return list(rows)

    async def has_report(self, incident_id: uuid.UUID) -> bool:
        async with self.sessions() as session:
            found = await session.scalar(select(Report.id).where(Report.incident_id == incident_id))
            return found is not None


async def build_lab(
    sessions: SessionFactory,
    database_url: str,
    tmp_path: Path,
    level: AutomationLevel,
    returncode: int,
    verify_timeout: float,
) -> AsyncIterator[Lab]:
    config = sentinel_config(tmp_path).model_copy(
        update={"actions": ActionsConfig(enabled=True, max_per_resource_per_hour=3)}
    )
    systemctl = FakeSystemctl("failed")
    runner = FakeActionRunner(systemctl, returncode)
    app = create_app(
        config,
        systemctl,
        NonceStore(tmp_path / "nonces.sqlite3", 300),
        config.load_secrets(),
        action_runner=runner,
    )
    async with transaction(sessions) as session:
        target = await add_target(
            session,
            "demo-1",
            "10.0.0.2",
            "https://demo-1:9443",
            Environment.LAB,
            KEY_ID,
            level,
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
    settings = Settings(
        database_url=database_url,
        sentinel_key_dir=tmp_path,
        execution_enabled=True,
        verify_settle_seconds=0,
        verify_poll_seconds=0.02,
        verify_timeout_seconds=verify_timeout,
    )
    source = StaticAlertSource()
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as sentinel_http,
        AsyncPostgresSaver.from_conn_string(settings.libpq_url) as checkpointer,
    ):
        await checkpointer.setup()
        runtime = build_runtime(
            settings, sessions, sentinel_http, RecordingLLM(happy_script(), sessions)
        )
        lab = Lab(
            sessions=sessions,
            settings=settings,
            runtime=runtime,
            sentinel_http=sentinel_http,
            systemctl=systemctl,
            runner=runner,
            source=source,
            ingestor=AlertIngestor(source, sessions, 2),
            checkpointer=checkpointer,
        )
        yield lab


@pytest.fixture
async def auto_lab(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[Lab]:
    async for lab in build_lab(sessions, database_url, tmp_path, AutomationLevel.AUTO_SAFE, 0, 5):
        yield lab


@pytest.fixture
async def approval_lab(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[Lab]:
    async for lab in build_lab(
        sessions, database_url, tmp_path, AutomationLevel.APPROVAL_REQUIRED, 0, 5
    ):
        yield lab


@pytest.fixture
async def failing_lab(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[Lab]:
    async for lab in build_lab(sessions, database_url, tmp_path, AutomationLevel.AUTO_SAFE, 1, 5):
        yield lab


@pytest.fixture
async def stubborn_lab(
    sessions: SessionFactory, database_url: str, tmp_path: Path
) -> AsyncIterator[Lab]:
    async for lab in build_lab(sessions, database_url, tmp_path, AutomationLevel.AUTO_SAFE, 0, 0.3):
        yield lab


async def test_auto_safe_lab_starts_the_service_and_verifies_recovery(auto_lab: Lab) -> None:
    incident_id = await auto_lab.open_incident()
    clearing = asyncio.create_task(auto_lab.clear_alerts_once_verifying(incident_id))
    await auto_lab.investigate(incident_id)
    await clearing

    assert await auto_lab.status(incident_id) == "RESOLVED"
    assert auto_lab.runner.calls == [START_ARGV]
    action = await auto_lab.chosen_action(incident_id)
    assert action.action_type == "start_service"
    assert action.status == "succeeded"
    assert action.authorization == f"policy:{action.policy_version}"
    assert action.result is not None
    assert action.result["after"]["active_state"] == "active"
    events = await auto_lab.event_types(incident_id)
    for expected in ("action_authorized", "action_dispatched", "action_succeeded"):
        assert expected in events
    assert events.index("action_dispatched") < events.index("action_succeeded")
    assert "verification_passed" in events
    assert await auto_lab.has_report(incident_id)
    async with auto_lab.sessions() as session:
        first_reading = await session.scalar(
            select(func.min(ToolCall.started_at)).where(
                ToolCall.incident_id == incident_id, ToolCall.agent == "executor"
            )
        )
    assert first_reading is not None
    assert first_reading < action.created_at


async def test_approval_is_bound_to_the_hash_and_then_executes(approval_lab: Lab) -> None:
    incident_id = await approval_lab.open_incident()
    await approval_lab.investigate(incident_id)

    assert await approval_lab.status(incident_id) == "AWAITING_APPROVAL"
    assert approval_lab.runner.calls == []
    assert not await approval_lab.has_report(incident_id)
    action = await approval_lab.chosen_action(incident_id)
    assert action.status == "pending_approval"

    async with transaction(approval_lab.sessions) as session:
        with pytest.raises(ApprovalConflict, match="changed"):
            await record_approval(
                session, incident_id, action.id, "approved", "alice", "0" * 64, None
            )
    async with transaction(approval_lab.sessions) as session:
        recorded = await record_approval(
            session, incident_id, action.id, "approved", "alice", action.action_hash, "go"
        )
    assert recorded.incident_status.value == "REMEDIATING"
    async with approval_lab.sessions() as session:
        job = await session.scalar(select(Job).where(Job.kind == REMEDIATE_JOB))
    assert job is not None
    assert job.payload == {"incident_id": str(incident_id), "action_id": str(action.id)}

    clearing = asyncio.create_task(approval_lab.clear_alerts_once_verifying(incident_id))
    await approval_lab.remediate(incident_id, action.id)
    await clearing

    assert await approval_lab.status(incident_id) == "RESOLVED"
    assert approval_lab.runner.calls == [START_ARGV]
    executed = await approval_lab.chosen_action(incident_id)
    assert executed.authorization == f"approval:{recorded.approval_id}"
    assert await approval_lab.has_report(incident_id)


async def test_a_rejected_action_never_runs_and_the_incident_escalates(approval_lab: Lab) -> None:
    incident_id = await approval_lab.open_incident()
    await approval_lab.investigate(incident_id)
    action = await approval_lab.chosen_action(incident_id)
    async with transaction(approval_lab.sessions) as session:
        await record_approval(
            session, incident_id, action.id, "rejected", "bob", action.action_hash, "not now"
        )
    await approval_lab.remediate(incident_id, action.id)

    incident = await approval_lab.incident(incident_id)
    assert incident.status == "ESCALATED"
    assert incident.escalation_reason == "approval_rejected"
    assert approval_lab.runner.calls == []
    assert (await approval_lab.chosen_action(incident_id)).status == "rejected"
    assert await approval_lab.has_report(incident_id)


async def test_a_service_that_recovered_before_dispatch_is_not_touched(approval_lab: Lab) -> None:
    incident_id = await approval_lab.open_incident()
    await approval_lab.investigate(incident_id)
    action = await approval_lab.chosen_action(incident_id)
    async with transaction(approval_lab.sessions) as session:
        await record_approval(
            session, incident_id, action.id, "approved", "alice", action.action_hash, None
        )
    approval_lab.systemctl.active_state = "active"
    clearing = asyncio.create_task(approval_lab.clear_alerts_once_verifying(incident_id))
    await approval_lab.remediate(incident_id, action.id)
    await clearing

    assert approval_lab.runner.calls == []
    assert (await approval_lab.chosen_action(incident_id)).status == "cancelled"
    assert await approval_lab.status(incident_id) == "RESOLVED"
    assert "action_cancelled" in await approval_lab.event_types(incident_id)


async def test_a_failed_action_escalates_without_a_retry(failing_lab: Lab) -> None:
    incident_id = await failing_lab.open_incident()
    await failing_lab.investigate(incident_id)

    incident = await failing_lab.incident(incident_id)
    assert incident.status == "ESCALATED"
    assert incident.escalation_reason == "action_failed"
    assert failing_lab.runner.calls == [START_ARGV]
    action = await failing_lab.chosen_action(incident_id)
    assert action.status == "failed"
    assert action.result_code == "EXIT_1"


async def test_alerts_that_keep_firing_try_the_next_rung_once_then_escalate(
    stubborn_lab: Lab,
) -> None:
    incident_id = await stubborn_lab.open_incident()
    await stubborn_lab.investigate(incident_id)

    incident = await stubborn_lab.incident(incident_id)
    assert incident.status == "ESCALATED"
    assert incident.escalation_reason == "not_recovered"
    events = await stubborn_lab.event_types(incident_id)
    assert events.count("verification_failed") == 2
    assert events.count("next_action_planned") == 1
    assert stubborn_lab.runner.calls == [START_ARGV, RESTART_ARGV]
    async with stubborn_lab.sessions() as session:
        taken = list(
            await session.scalars(
                select(ActionRow.action_type)
                .where(ActionRow.incident_id == incident_id, ActionRow.status == "succeeded")
                .order_by(ActionRow.finished_at)
            )
        )
    assert taken == ["start_service", "restart_service"]


async def test_the_next_rung_waits_for_a_person_when_it_is_not_automatic(
    stubborn_lab: Lab,
) -> None:
    async with transaction(stubborn_lab.sessions) as session:
        await session.execute(
            update(Target).where(Target.name == "demo-1").values(auto_actions=["start_service"])
        )
    incident_id = await stubborn_lab.open_incident()
    await stubborn_lab.investigate(incident_id)

    assert await stubborn_lab.status(incident_id) == "AWAITING_APPROVAL"
    assert stubborn_lab.runner.calls == [START_ARGV]
    async with stubborn_lab.sessions() as session:
        pending = await session.scalar(
            select(ActionRow).where(
                ActionRow.incident_id == incident_id, ActionRow.status == "pending_approval"
            )
        )
    assert pending is not None
    assert pending.action_type == "restart_service"


@pytest.fixture
async def api(sessions: SessionFactory) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(API_TOKEN))
    app = create_api(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def test_the_api_records_a_decision_and_refuses_a_stale_hash(
    approval_lab: Lab, api: httpx.AsyncClient
) -> None:
    incident_id = await approval_lab.open_incident()
    await approval_lab.investigate(incident_id)
    detail = (await api.get(f"/api/incidents/{incident_id}", headers=API_AUTH)).json()
    pending = [a for a in detail["actions"] if a["status"] == "pending_approval"]
    assert len(pending) == 1
    path = f"/api/incidents/{incident_id}/actions/{pending[0]['id']}/decision"
    body: dict[str, str] = {"decision": "approved", "action_hash": "0" * 64}

    named = await api.post(path, json={**body, "decided_by": "alice"}, headers=API_AUTH)
    assert named.status_code == 422
    stale = await api.post(path, json=body, headers=API_AUTH)
    assert stale.status_code == 409
    unauthenticated = await api.post(path, json=body)
    assert unauthenticated.status_code == 401

    body["action_hash"] = pending[0]["action_hash"]
    accepted = await api.post(path, json=body, headers=API_AUTH)
    assert accepted.status_code == 200
    assert accepted.json()["incident_status"] == "REMEDIATING"
    async with approval_lab.sessions() as session:
        approver = await session.scalar(select(Approval.decided_by))
    assert approver == "api-token"
    again = await api.post(path, json=body, headers=API_AUTH)
    assert again.status_code == 409
