import hashlib
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import (
    ActionRow,
    DiagnosisRow,
    FindingRow,
    Incident,
    ManagedResourceRow,
    Target,
    ToolCall,
)
from noc.policy.engine import PolicyInputs, evaluate_safely
from noc.policy.loader import PolicyDocument
from noc.policy.models import (
    ActionCandidate,
    AutomationLevel,
    Decision,
    Environment,
    ResourceFacts,
    ServiceProfile,
    SituationFacts,
    TargetFacts,
)
from noc_shared.permissions import PermissionClass

IN_FLIGHT_STATUSES = ("dispatched", "executing", "outcome_unknown")
EXECUTED_STATUSES = ("dispatched", "executing", "succeeded", "failed", "outcome_unknown")


def action_hash(incident_id: uuid.UUID, target_id: uuid.UUID, candidate: ActionCandidate) -> str:
    canonical = json.dumps(
        {
            "incident": str(incident_id),
            "target": str(target_id),
            "action": candidate.action_type,
            "resource": candidate.resource_id,
            "params": candidate.params,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def evidence_age_seconds(session: AsyncSession, incident_id: uuid.UUID) -> float:
    latest = await session.scalar(
        select(func.max(ToolCall.started_at)).where(
            ToolCall.incident_id == incident_id, ToolCall.ok.is_(True)
        )
    )
    if latest is None:
        return float("inf")
    return (utc_now() - latest).total_seconds()


async def situation_facts(
    session: AsyncSession,
    incident: Incident,
    diagnosis: DiagnosisRow,
    action_type: str,
    execution_enabled: bool,
    automation_paused: bool,
) -> SituationFacts:
    in_flight = await session.scalar(
        select(func.count())
        .select_from(ActionRow)
        .where(ActionRow.target_id == incident.target_id, ActionRow.status.in_(IN_FLIGHT_STATUSES))
    )
    attempts = await session.scalar(
        select(func.count())
        .select_from(ActionRow)
        .where(
            ActionRow.incident_id == incident.id,
            ActionRow.action_type == action_type,
            ActionRow.status.in_(EXECUTED_STATUSES),
        )
    )
    injection = await session.scalar(
        select(func.count())
        .select_from(FindingRow)
        .where(FindingRow.incident_id == incident.id, FindingRow.suspected_injection.is_(True))
    )
    return SituationFacts(
        global_kill_switch=automation_paused,
        execution_enabled=execution_enabled,
        evidence_age_seconds=await evidence_age_seconds(session, incident.id),
        action_in_flight_on_host=bool(in_flight),
        previous_attempts_of_type=attempts or 0,
        is_security_incident=diagnosis.is_security_incident,
        diagnosis_confidence=diagnosis.confidence,
        suspected_injection=bool(injection),
    )


def target_facts(target: Target) -> TargetFacts:
    return TargetFacts(
        environment=Environment(target.environment),
        automation_level=AutomationLevel(target.automation_level),
        auto_actions=tuple(target.auto_actions),
        halted=target.halted,
    )


def resource_facts(
    resource: ManagedResourceRow | None, resource_id: str, policy: PolicyDocument
) -> ResourceFacts:
    if resource is None:
        return ResourceFacts(registered=False, protected=resource_id in policy.protected_resources)
    return ResourceFacts(
        registered=True,
        allowed_actions=tuple(resource.allowed_actions),
        protected=resource_id in policy.protected_resources,
        profile=ServiceProfile.model_validate(resource.profile) if resource.profile else None,
    )


async def supporting_refs(session: AsyncSession, incident_id: uuid.UUID) -> tuple[str, ...]:
    findings = await session.scalars(
        select(FindingRow).where(FindingRow.incident_id == incident_id)
    )
    return tuple(sorted({e["tool_call_ref"] for f in findings for e in f.evidence}))


async def decide_actions(
    session: AsyncSession,
    incident: Incident,
    diagnosis: DiagnosisRow,
    affected_resource_id: str | None,
    policy: PolicyDocument,
    execution_enabled: bool,
    automation_paused: bool,
) -> list[Decision]:
    target = await session.get_one(Target, incident.target_id)
    resource_id = affected_resource_id or ""
    resource = await session.get(ManagedResourceRow, (incident.target_id, resource_id))
    refs = await supporting_refs(session, incident.id)
    decisions: list[Decision] = []

    for action_type in policy.candidate_actions(diagnosis.primary_code):
        candidate = ActionCandidate(
            action_type=action_type, resource_id=resource_id, evidence_refs=refs
        )
        situation = await situation_facts(
            session, incident, diagnosis, action_type, execution_enabled, automation_paused
        )
        inputs = PolicyInputs(
            candidate=candidate,
            definition=policy.actions.get(action_type),
            target=target_facts(target),
            resource=resource_facts(resource, resource_id, policy),
            situation=situation,
        )
        decision = evaluate_safely(inputs, policy.weights, policy.version)
        decisions.append(decision)
        session.add(action_row(incident, candidate, decision))
    await session.flush()
    return decisions


def action_row(incident: Incident, candidate: ActionCandidate, decision: Decision) -> ActionRow:
    return ActionRow(
        incident_id=incident.id,
        target_id=incident.target_id,
        action_type=candidate.action_type,
        resource_id=candidate.resource_id,
        params=dict(candidate.params),
        status="proposed" if decision.eligible else "ineligible",
        permission_class=PermissionClass(decision.permission_class).name,
        eligible=decision.eligible,
        auto_executable=decision.auto_executable,
        gate_failures=[gate.value for gate in decision.gate_failures],
        reasons=decision.reasons,
        impact_score=decision.impact.score,
        high_impact=decision.high_impact,
        policy_version=decision.policy_version,
        action_hash=action_hash(incident.id, incident.target_id, candidate),
    )


async def decisions_exist(session: AsyncSession, incident_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(ActionRow.id).where(ActionRow.incident_id == incident_id).limit(1)
    )
    return found is not None
