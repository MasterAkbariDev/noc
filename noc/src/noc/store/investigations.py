import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, String, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noc.agents.diagnosis import FindingView
from noc.agents.investigator import InvestigationOutcome
from noc.agents.loop import AgentStats
from noc.agents.schemas import Diagnosis, Finding
from noc.db.base import utc_now
from noc.db.models import AgentRun, DiagnosisRow, FindingRow, Incident, Job


async def save_investigation(
    session: AsyncSession,
    incident: Incident,
    agent: str,
    agent_run: AgentRun,
    outcome: InvestigationOutcome,
) -> DiagnosisRow:
    report = outcome.grounded.report
    finish_run(agent_run, outcome.stats)
    add_findings(session, incident.id, agent, report.findings)
    return await persist_diagnosis(
        session, incident, report.diagnosis, outcome.grounded.dropped_findings
    )


def finish_run(agent_run: AgentRun, stats: AgentStats) -> None:
    agent_run.status = "succeeded"
    agent_run.ended_at = utc_now()
    agent_run.rounds = stats.rounds
    agent_run.llm_calls = stats.llm_calls
    agent_run.tool_calls = stats.tool_calls


def mark_run_failed(agent_run: AgentRun, error: str) -> None:
    agent_run.status = "failed"
    agent_run.ended_at = utc_now()
    agent_run.error = error


ORPHANED_RUN_ERROR = "orphaned: the job running it stopped (worker restart or lost lease)"


async def fail_orphaned_runs(session: AsyncSession, job_kind: str) -> int:
    live_job = select(Job.id).where(
        Job.kind == job_kind,
        Job.status == "running",
        Job.lease_expires_at > func.now(),
        Job.payload["incident_id"].astext == AgentRun.incident_id.cast(String),
    )
    statement = (
        update(AgentRun)
        .where(AgentRun.status == "running", ~exists(live_job))
        .values(status="failed", ended_at=utc_now(), error=ORPHANED_RUN_ERROR)
    )
    result = cast(CursorResult[Any], await session.execute(statement))
    return result.rowcount


def add_findings(
    session: AsyncSession, incident_id: uuid.UUID, agent: str, findings: list[Finding]
) -> None:
    for finding in findings:
        session.add(
            FindingRow(
                incident_id=incident_id,
                agent=agent,
                label=finding.id,
                category=finding.category.value,
                severity=finding.severity.value,
                summary=finding.summary,
                evidence=[evidence.model_dump() for evidence in finding.evidence],
                evidence_strength=finding.evidence_strength.value,
                counter_evidence=finding.counter_evidence,
                confidence=finding.confidence,
                suspected_injection=finding.suspected_injection,
                grounded=True,
            )
        )


async def persist_diagnosis(
    session: AsyncSession,
    incident: Incident,
    diagnosis: Diagnosis,
    ungrounded_findings: int,
) -> DiagnosisRow:
    primary = diagnosis.primary()
    row = DiagnosisRow(
        incident_id=incident.id,
        primary_code=primary.root_cause_code.value,
        confidence=primary.confidence,
        is_security_incident=diagnosis.is_security_incident,
        hypotheses=[hypothesis.model_dump(mode="json") for hypothesis in diagnosis.hypotheses],
        needs_more_info=diagnosis.needs_more_info,
        ungrounded_findings=ungrounded_findings,
    )
    session.add(row)
    incident.root_cause_code = primary.root_cause_code.value
    incident.root_cause_summary = primary.description
    incident.confidence = primary.confidence
    await session.flush()
    return row


def new_agent_run(incident_id: uuid.UUID, agent: str) -> AgentRun:
    return AgentRun(incident_id=incident_id, agent=agent, status="running")


def finding_view(row: FindingRow) -> FindingView:
    return FindingView.model_validate(
        {
            "label": row.label,
            "category": row.category,
            "severity": row.severity,
            "summary": row.summary,
            "evidence": row.evidence,
            "evidence_strength": row.evidence_strength,
            "counter_evidence": row.counter_evidence,
            "confidence": row.confidence,
            "suspected_injection": row.suspected_injection,
        }
    )
