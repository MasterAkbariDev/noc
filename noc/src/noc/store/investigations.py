import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from noc.agents.investigator import InvestigationOutcome
from noc.db.base import utc_now
from noc.db.models import AgentRun, DiagnosisRow, FindingRow, Incident


async def save_investigation(
    session: AsyncSession,
    incident: Incident,
    agent: str,
    agent_run: AgentRun,
    outcome: InvestigationOutcome,
) -> DiagnosisRow:
    report = outcome.grounded.report
    agent_run.status = "succeeded"
    agent_run.ended_at = utc_now()
    agent_run.rounds = outcome.stats.rounds
    agent_run.llm_calls = outcome.stats.llm_calls
    agent_run.tool_calls = outcome.stats.tool_calls

    for finding in report.findings:
        session.add(
            FindingRow(
                incident_id=incident.id,
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

    primary = report.diagnosis.primary()
    diagnosis = DiagnosisRow(
        incident_id=incident.id,
        primary_code=primary.root_cause_code.value,
        confidence=primary.confidence,
        is_security_incident=report.diagnosis.is_security_incident,
        hypotheses=[
            hypothesis.model_dump(mode="json") for hypothesis in report.diagnosis.hypotheses
        ],
        needs_more_info=report.diagnosis.needs_more_info,
        ungrounded_findings=outcome.grounded.dropped_findings,
    )
    session.add(diagnosis)
    incident.root_cause_code = primary.root_cause_code.value
    incident.root_cause_summary = primary.description
    incident.confidence = primary.confidence
    await session.flush()
    return diagnosis


def new_agent_run(incident_id: uuid.UUID, agent: str) -> AgentRun:
    return AgentRun(incident_id=incident_id, agent=agent, status="running")
