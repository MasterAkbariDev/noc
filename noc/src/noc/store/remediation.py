import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import ActionRow, Approval, Incident
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.jobs.queue import enqueue
from noc.store.incidents import add_event, lock_incident, transition

REMEDIATE_JOB = "remediate"
EXECUTABLE_ACTIONS = frozenset({"start_service", "restart_service"})

PROPOSED = "proposed"
PENDING_APPROVAL = "pending_approval"
AUTHORIZED = "authorized"
DISPATCHED = "dispatched"
SUCCEEDED = "succeeded"
FAILED = "failed"
REFUSED = "refused"
OUTCOME_UNKNOWN = "outcome_unknown"
CANCELLED = "cancelled"
REJECTED = "rejected"
EXPIRED = "expired"
CURRENT_STATUSES = (
    PENDING_APPROVAL,
    AUTHORIZED,
    DISPATCHED,
    SUCCEEDED,
    FAILED,
    REFUSED,
    OUTCOME_UNKNOWN,
    CANCELLED,
    REJECTED,
    EXPIRED,
)

PLANNER = "planner"
SWEEPER = "approval-sweeper"

ApprovalDecision = Literal["approved", "rejected"]
PlanOutcome = Literal["remediate", "awaiting_approval", "none"]


class ApprovalConflict(Exception):
    pass


@dataclass(frozen=True)
class ApprovalRecorded:
    approval_id: uuid.UUID
    incident_status: IncidentStatus


def remediation_dedupe_key(action_id: uuid.UUID) -> str:
    return f"remediate:{action_id}"


async def enqueue_remediation(
    session: AsyncSession, incident_id: uuid.UUID, action_id: uuid.UUID
) -> None:
    await enqueue(
        session,
        kind=REMEDIATE_JOB,
        payload={"incident_id": str(incident_id), "action_id": str(action_id)},
        dedupe_key=remediation_dedupe_key(action_id),
        priority=10,
    )


async def best_candidate(session: AsyncSession, incident_id: uuid.UUID) -> ActionRow | None:
    return await session.scalar(
        select(ActionRow)
        .where(
            ActionRow.incident_id == incident_id,
            ActionRow.eligible.is_(True),
            ActionRow.status == PROPOSED,
            ActionRow.action_type.in_(EXECUTABLE_ACTIONS),
        )
        .order_by(ActionRow.rung, ActionRow.impact_score, ActionRow.action_type)
        .limit(1)
    )


async def current_action(session: AsyncSession, incident_id: uuid.UUID) -> ActionRow | None:
    return await session.scalar(
        select(ActionRow)
        .where(ActionRow.incident_id == incident_id, ActionRow.status.in_(CURRENT_STATUSES))
        .limit(1)
    )


async def plan_remediation(
    session: AsyncSession, incident: Incident, approval_ttl_seconds: int
) -> PlanOutcome:
    action = await best_candidate(session, incident.id)
    if action is None:
        return "none"
    if action.auto_executable:
        action.status = AUTHORIZED
        action.authorization = f"policy:{action.policy_version}"
        await transition(session, incident, IncidentStatus.REMEDIATING, PLANNER)
        await add_event(session, incident.id, "action_authorized", PLANNER, action_summary(action))
        return "remediate"
    action.status = PENDING_APPROVAL
    action.approval_expires_at = utc_now() + timedelta(seconds=approval_ttl_seconds)
    await transition(session, incident, IncidentStatus.AWAITING_APPROVAL, PLANNER)
    payload = {**action_summary(action), "expires_at": action.approval_expires_at.isoformat()}
    await add_event(session, incident.id, "approval_requested", PLANNER, payload)
    return "awaiting_approval"


def action_summary(action: ActionRow) -> dict[str, object]:
    return {
        "action_id": str(action.id),
        "action_type": action.action_type,
        "resource_id": action.resource_id,
        "permission_class": action.permission_class,
        "impact_score": action.impact_score,
        "action_hash": action.action_hash,
    }


async def record_approval(
    session: AsyncSession,
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    decision: ApprovalDecision,
    decided_by: str,
    action_hash: str,
    comment: str | None,
) -> ApprovalRecorded:
    incident = await lock_incident(session, incident_id)
    if IncidentStatus(incident.status) is not IncidentStatus.AWAITING_APPROVAL:
        raise ApprovalConflict("the incident is not waiting for an approval")
    action = await session.get(ActionRow, action_id, with_for_update=True)
    if action is None or action.incident_id != incident_id or action.status != PENDING_APPROVAL:
        raise ApprovalConflict("this action is not waiting for an approval")
    if action.approval_expires_at is not None and action.approval_expires_at <= utc_now():
        raise ApprovalConflict("the approval request has expired")
    if action_hash != action.action_hash:
        raise ApprovalConflict("the action changed since it was shown; reload it")
    approval = Approval(
        action_id=action.id,
        incident_id=incident_id,
        decision=decision,
        decided_by=decided_by,
        comment=comment,
        action_hash=action.action_hash,
        policy_version=action.policy_version,
    )
    session.add(approval)
    await session.flush()
    if decision == "approved":
        action.status = AUTHORIZED
        action.authorization = f"approval:{approval.id}"
        await transition(session, incident, IncidentStatus.REMEDIATING, decided_by)
    else:
        action.status = REJECTED
        await transition(
            session,
            incident,
            IncidentStatus.ESCALATED,
            decided_by,
            EscalationReason.APPROVAL_REJECTED,
        )
    payload = {**action_summary(action), "decision": decision, "comment": comment}
    await add_event(session, incident_id, "approval_decided", decided_by, payload)
    await enqueue_remediation(session, incident_id, action.id)
    return ApprovalRecorded(approval.id, IncidentStatus(incident.status))


async def expire_approvals(session: AsyncSession) -> int:
    expired = list(
        await session.scalars(
            select(ActionRow).where(
                ActionRow.status == PENDING_APPROVAL, ActionRow.approval_expires_at <= utc_now()
            )
        )
    )
    for action in expired:
        incident = await lock_incident(session, action.incident_id)
        action.status = EXPIRED
        if IncidentStatus(incident.status) is IncidentStatus.AWAITING_APPROVAL:
            await transition(
                session,
                incident,
                IncidentStatus.ESCALATED,
                SWEEPER,
                EscalationReason.APPROVAL_EXPIRED,
            )
        await add_event(session, incident.id, "approval_expired", SWEEPER, action_summary(action))
        await enqueue_remediation(session, incident.id, action.id)
    return len(expired)
