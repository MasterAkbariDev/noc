import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import ActionRow, DiagnosisRow, Incident, ManagedResourceRow, Target
from noc.db.session import transaction
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.orchestration.action_checks import CheckReading, read_check
from noc.orchestration.nodes import POLICY, Update, incident_id_of
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState
from noc.policy.models import ActionCheck
from noc.store.briefs import all_alerts_resolved, target_ref
from noc.store.decisions import reevaluate_action
from noc.store.incidents import add_event, lock_incident, transition
from noc.store.remediation import (
    AUTHORIZED,
    CANCELLED,
    DISPATCHED,
    FAILED,
    OUTCOME_UNKNOWN,
    REFUSED,
    SUCCEEDED,
    action_summary,
    actions_taken,
    apply_decision,
    current_action,
    plan_remediation,
    remaining_candidates,
)
from noc.tools.catalog import EXECUTOR
from noc.tools.sentinel_client import ActionReply, SentinelClient
from noc.tools.spec import TargetRef, ToolContext
from noc_shared.actions import ActionRequest

VERIFIER = "verifier"
APPROVAL_PREFIX = "approval:"
SETTLE_POLLS = 72
SETTLE_POLL_SECONDS = 5.0

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class CheckTarget:
    check: ActionCheck
    resource_id: str
    resource_name: str


@dataclass(frozen=True)
class Dispatch:
    action_id: uuid.UUID
    action_type: str
    request: ActionRequest
    target: TargetRef


def action_request(action: ActionRow, incident_id: uuid.UUID) -> ActionRequest:
    authorization = action.authorization or ""
    approval_id = (
        uuid.UUID(authorization.removeprefix(APPROVAL_PREFIX))
        if authorization.startswith(APPROVAL_PREFIX)
        else None
    )
    return ActionRequest(
        action_id=action.id,
        attempt_id=action.attempt_id or uuid.uuid4(),
        incident_id=incident_id,
        attempt=action.attempt,
        action_hash=action.action_hash,
        resource_id=action.resource_id,
        params=dict(action.params),
        approval_id=approval_id,
        auto_policy_ref=None if approval_id else authorization,
    )


def still_executing(reply: ActionReply) -> bool:
    return (
        reply.kind == "result" and reply.result is not None and reply.result.status == "executing"
    )


async def settle_action(
    client: SentinelClient,
    action_type: str,
    request: ActionRequest,
    sleep: Sleep | None = None,
    polls: int = 0,
) -> ActionReply:
    reply = await client.run_action(action_type, request)
    if reply.kind != "unknown" and not still_executing(reply):
        return reply
    lookup = await client.get_action(request.action_id)
    for _ in range(polls if sleep is not None else 0):
        if not still_executing(lookup) or sleep is None:
            break
        await sleep(SETTLE_POLL_SECONDS)
        lookup = await client.get_action(request.action_id)
    if lookup.kind == "result" and lookup.result and lookup.result.status != "executing":
        return lookup
    if lookup.kind == "not_found":
        again = await client.run_action(action_type, request)
        if again.kind == "result" and again.result and again.result.status != "executing":
            return again
        return ActionReply("unknown", detail=again.detail or reply.detail)
    return ActionReply("unknown", detail=reply.detail or lookup.detail)


async def latest_diagnosis(session: AsyncSession, incident_id: uuid.UUID) -> DiagnosisRow | None:
    return await session.scalar(
        select(DiagnosisRow)
        .where(DiagnosisRow.incident_id == incident_id)
        .order_by(DiagnosisRow.created_at.desc())
        .limit(1)
    )


class RemediationNodes:
    def __init__(self, runtime: Runtime, sleep: Sleep = asyncio.sleep) -> None:
        self._runtime = runtime
        self._sessions = runtime.sessions
        self._sleep = sleep

    async def execute(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.REMEDIATING:
                return {}
            action = await current_action(session, incident_id)
            if action is None or action.status not in (AUTHORIZED, DISPATCHED):
                await self._escalate(session, incident, EscalationReason.EXECUTION_NOT_AVAILABLE)
                return {"outcome": "escalated"}
            needs_snapshot = action.status == AUTHORIZED
            target = target_ref(await session.get_one(Target, incident.target_id))
            trace_id = incident.trace_id
            check_target = await self._check_target(session, incident, action)
        if needs_snapshot:
            snapshot = await self._probe(incident_id, target, trace_id, check_target)
            outcome = await self._authorize_dispatch(incident_id, snapshot)
            if outcome is not None:
                return outcome
        dispatch = await self._load_dispatch(incident_id, target)
        if dispatch is None:
            return {}
        client = self._runtime.sentinels.client_for(dispatch.target)
        reply = await settle_action(
            client, dispatch.action_type, dispatch.request, self._sleep, SETTLE_POLLS
        )
        return await self._record_reply(incident_id, dispatch.action_id, reply)

    async def _check_target(
        self, session: AsyncSession, incident: Incident, action: ActionRow
    ) -> CheckTarget:
        definition = self._runtime.policy.actions.get(action.action_type)
        check = definition.check if definition is not None else ActionCheck.SERVICE_ACTIVE
        resource = await session.get(ManagedResourceRow, (incident.target_id, action.resource_id))
        name = resource.name if resource is not None else ""
        return CheckTarget(check=check, resource_id=action.resource_id, resource_name=name)

    async def _probe(
        self, incident_id: uuid.UUID, target: TargetRef, trace_id: str, check_target: CheckTarget
    ) -> CheckReading:
        context = ToolContext(
            incident_id=incident_id, agent=EXECUTOR, target=target, trace_id=trace_id
        )
        return await read_check(
            self._runtime.registry,
            context,
            check_target.check,
            check_target.resource_id,
            check_target.resource_name,
        )

    async def _authorize_dispatch(
        self, incident_id: uuid.UUID, snapshot: CheckReading
    ) -> Update | None:
        settings = self._runtime.settings
        policy = self._runtime.policy
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.REMEDIATING:
                return {}
            action = await current_action(session, incident_id)
            if action is None or action.status != AUTHORIZED:
                return None
            if not snapshot.ok:
                await self._cancel(
                    session, incident, action, f"pre-action snapshot failed: {snapshot.error}"
                )
                await self._escalate(session, incident, EscalationReason.TARGET_UNREACHABLE)
                return {"outcome": "escalated"}
            if action.action_type == "start_service" and snapshot.active_state == "active":
                await self._cancel(session, incident, action, "the service is already active")
                await transition(session, incident, IncidentStatus.VERIFYING, EXECUTOR)
                return {"outcome": "verify"}
            if action.policy_version != policy.version:
                await self._cancel(
                    session, incident, action, "the policy changed since the decision"
                )
                await self._escalate(session, incident, EscalationReason.ACTION_BLOCKED)
                return {"outcome": "escalated"}
            diagnosis = await latest_diagnosis(session, incident_id)
            if diagnosis is None:
                await self._escalate(session, incident, EscalationReason.EXECUTION_NOT_AVAILABLE)
                return {"outcome": "escalated"}
            decision = await reevaluate_action(
                session,
                incident,
                diagnosis,
                action,
                policy,
                settings.execution_enabled,
                settings.automation_paused,
            )
            approved = (action.authorization or "").startswith(APPROVAL_PREFIX)
            allowed = decision.eligible and (approved or decision.auto_executable)
            if not allowed:
                reasons = [gate.value for gate in decision.gate_failures] or decision.reasons
                await self._cancel(
                    session, incident, action, "gates failed at dispatch: " + ", ".join(reasons)
                )
                await self._escalate(session, incident, EscalationReason.ACTION_BLOCKED)
                return {"outcome": "escalated"}
            action.status = DISPATCHED
            action.dispatched_at = utc_now()
            action.attempt_id = uuid.uuid4()
            await add_event(
                session, incident_id, "action_dispatched", EXECUTOR, action_summary(action)
            )
        return None

    async def _load_dispatch(self, incident_id: uuid.UUID, target: TargetRef) -> Dispatch | None:
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.REMEDIATING:
                return None
            action = await current_action(session, incident_id)
            if action is None or action.status != DISPATCHED:
                return None
            if action.attempt_id is None:
                action.attempt_id = uuid.uuid4()
            return Dispatch(
                action.id, action.action_type, action_request(action, incident_id), target
            )

    async def _record_reply(
        self, incident_id: uuid.UUID, action_id: uuid.UUID, reply: ActionReply
    ) -> Update:
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.REMEDIATING:
                return {}
            action = await session.get(ActionRow, action_id, with_for_update=True)
            if action is None or action.status != DISPATCHED:
                return {}
            action.finished_at = utc_now()
            result = reply.result
            if result is not None:
                action.result = result.model_dump(mode="json")
                action.result_code = result.code
            payload = {**action_summary(action), "detail": reply.detail}
            if reply.kind == "result" and result is not None and result.status == "succeeded":
                action.status = SUCCEEDED
                await add_event(session, incident_id, "action_succeeded", EXECUTOR, payload)
                await transition(session, incident, IncidentStatus.VERIFYING, EXECUTOR)
                return {"outcome": "verify"}
            if (
                reply.kind == "result"
                and result is not None
                and result.status in ("failed", "refused")
            ):
                action.status = FAILED if result.status == "failed" else REFUSED
                await add_event(session, incident_id, "action_failed", EXECUTOR, payload)
            elif reply.kind == "not_found":
                action.status = FAILED
                action.result_code = "ACTIONS_UNAVAILABLE"
                await add_event(session, incident_id, "action_failed", EXECUTOR, payload)
            else:
                action.status = OUTCOME_UNKNOWN
                action.result_code = "OUTCOME_UNKNOWN"
                await add_event(session, incident_id, "action_outcome_unknown", EXECUTOR, payload)
            await self._escalate(session, incident, EscalationReason.ACTION_FAILED)
        return {"outcome": "escalated"}

    async def verify(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        settings = self._runtime.settings
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.VERIFYING:
                return {}
            action = await current_action(session, incident_id)
            if action is None:
                await self._escalate(session, incident, EscalationReason.NOT_RECOVERED)
                return {"outcome": "escalated"}
            started = action.finished_at or utc_now()
            target = target_ref(await session.get_one(Target, incident.target_id))
            trace_id = incident.trace_id
            check_target = await self._check_target(session, incident, action)
            timeout = self._verify_timeout(action.action_type)
        settle_until = started + timedelta(seconds=settings.verify_settle_seconds)
        deadline = started + timedelta(seconds=timeout)
        while True:
            now = utc_now()
            if now < settle_until:
                await self._sleep((settle_until - now).total_seconds())
                continue
            reading = await self._probe(incident_id, target, trace_id, check_target)
            async with transaction(self._sessions) as session:
                alerts_clear = await all_alerts_resolved(session, incident_id)
            checks = {"alerts_resolved": alerts_clear}
            if check_target.check is not ActionCheck.NONE:
                checks = {check_target.check.value: reading.ok and reading.passed, **checks}
            if all(checks.values()):
                return await self._finish_verification(incident_id, checks, passed=True)
            if utc_now() >= deadline:
                return await self._finish_verification(incident_id, checks, passed=False)
            await self._sleep(settings.verify_poll_seconds)

    def _verify_timeout(self, action_type: str) -> float:
        definition = self._runtime.policy.actions.get(action_type)
        if definition is not None and definition.verify_timeout_seconds is not None:
            return float(definition.verify_timeout_seconds)
        return self._runtime.settings.verify_timeout_seconds

    async def _finish_verification(
        self, incident_id: uuid.UUID, checks: dict[str, bool], passed: bool
    ) -> Update:
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.VERIFYING:
                return {}
            if passed:
                await add_event(session, incident_id, "verification_passed", VERIFIER, checks)
                await transition(session, incident, IncidentStatus.RESOLVED, VERIFIER)
                return {"outcome": "resolved"}
            await add_event(session, incident_id, "verification_failed", VERIFIER, checks)
            planned = await self._plan_next_rung(session, incident)
            if planned is not None:
                return {"outcome": planned}
            await self._escalate(session, incident, EscalationReason.NOT_RECOVERED)
        return {"outcome": "escalated"}

    async def _plan_next_rung(self, session: AsyncSession, incident: Incident) -> str | None:
        policy = self._runtime.policy
        settings = self._runtime.settings
        if await actions_taken(session, incident.id) >= policy.max_actions_per_incident:
            return None
        diagnosis = await latest_diagnosis(session, incident.id)
        previous = await current_action(session, incident.id)
        if diagnosis is None or previous is None:
            return None
        chosen: ActionRow | None = None
        for candidate in await remaining_candidates(session, incident.id):
            decision = await reevaluate_action(
                session,
                incident,
                diagnosis,
                candidate,
                policy,
                settings.execution_enabled,
                settings.automation_paused,
            )
            apply_decision(candidate, decision)
            if decision.eligible:
                chosen = candidate
                break
        if chosen is None:
            return None
        payload = {
            **action_summary(chosen),
            "previous_action_type": previous.action_type,
            "previous_resource_id": previous.resource_id,
        }
        await add_event(session, incident.id, "next_action_planned", POLICY, payload)
        await transition(session, incident, IncidentStatus.DIAGNOSED, VERIFIER)
        await transition(session, incident, IncidentStatus.PLANNED, POLICY)
        planned = await plan_remediation(session, incident, settings.approval_ttl_seconds)
        return None if planned == "none" else planned

    async def _cancel(
        self, session: AsyncSession, incident: Incident, action: ActionRow, reason: str
    ) -> None:
        action.status = CANCELLED
        action.reasons = [*action.reasons, reason]
        payload = {**action_summary(action), "reason": reason}
        await add_event(session, incident.id, "action_cancelled", EXECUTOR, payload)

    async def _escalate(
        self, session: AsyncSession, incident: Incident, reason: EscalationReason
    ) -> None:
        await transition(session, incident, IncidentStatus.ESCALATED, EXECUTOR, reason)
