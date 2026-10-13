from typing import Any, cast

import pytest
from sqlalchemy import func, select, text

from noc.config import Settings
from noc.db.models import AgentRun, Incident, IncidentEvent, Job
from noc.db.session import SessionFactory, transaction
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.ingest import AlertIngestor
from noc.jobs import queue
from noc.orchestration.graph import IncidentGraph
from noc.store.investigations import new_agent_run
from noc.worker.main import Worker
from tests.integration.test_alert_ingestion import (
    StaticAlertSource,
    register_demo_target,
)
from tests.support.builders import prometheus_alert

pytestmark = pytest.mark.integration


class BrokenGraph:
    async def aget_state(self, config: Any) -> Any:
        raise RuntimeError("provider said 400")


async def test_a_dead_job_escalates_its_incident(sessions: SessionFactory) -> None:
    await register_demo_target(sessions)
    source = StaticAlertSource()
    source.alerts = [prometheus_alert()]
    await AlertIngestor(source, sessions, 2).poll_once()
    async with transaction(sessions) as session:
        await session.execute(text("UPDATE jobs SET max_attempts = 1"))
        incident_id = await session.scalar(select(Incident.id))
        assert incident_id is not None
        await session.execute(
            text("UPDATE incidents SET status = 'INVESTIGATING' WHERE id = :id"),
            {"id": incident_id},
        )
        session.add(new_agent_run(incident_id, "metrics"))

    worker = Worker(
        Settings(),
        sessions,
        cast(IncidentGraph, BrokenGraph()),
        cast(AlertIngestor, None),
    )
    async with transaction(sessions) as session:
        job = await queue.claim(session, worker._identity, [INVESTIGATE_JOB], 60)
    assert job is not None
    await worker._slots.acquire()
    await worker._handle(job)

    async with sessions() as session:
        incident = await session.get_one(Incident, incident_id)
        assert incident.status == "ESCALATED"
        assert incident.escalation_reason == "investigation_failed"
        runs = list(await session.scalars(select(AgentRun.status)))
        assert runs == ["failed"]
        abandoned = await session.scalar(
            select(func.count())
            .select_from(IncidentEvent)
            .where(IncidentEvent.type == "investigation_abandoned")
        )
        assert abandoned == 1


async def test_a_retryable_failure_leaves_the_incident_alone(sessions: SessionFactory) -> None:
    await register_demo_target(sessions)
    source = StaticAlertSource()
    source.alerts = [prometheus_alert()]
    await AlertIngestor(source, sessions, 2).poll_once()
    worker = Worker(
        Settings(), sessions, cast(IncidentGraph, BrokenGraph()), cast(AlertIngestor, None)
    )
    async with transaction(sessions) as session:
        job = await queue.claim(session, worker._identity, [INVESTIGATE_JOB], 60)
    assert job is not None
    await worker._slots.acquire()
    await worker._handle(job)
    async with sessions() as session:
        assert await session.scalar(select(Incident.status)) == "NEW"
        assert await session.scalar(select(Job.status)) == "queued"
