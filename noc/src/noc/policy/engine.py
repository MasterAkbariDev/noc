from dataclasses import dataclass

from noc.policy.models import (
    ActionCandidate,
    ActionDefinition,
    AutomationLevel,
    Criticality,
    Decision,
    Environment,
    Gate,
    Impact,
    Redundancy,
    ResourceFacts,
    ScoreWeights,
    SituationFacts,
    TargetFacts,
)
from noc_shared.permissions import PermissionClass

FRESHNESS_LIMIT_SECONDS = 60.0
LOW_CONFIDENCE_THRESHOLD = 0.7
UNCERTAIN_CONFIDENCE_THRESHOLD = 0.6
SLO_BURN_PENALTY = 5


@dataclass(frozen=True)
class PolicyInputs:
    candidate: ActionCandidate
    definition: ActionDefinition | None
    target: TargetFacts
    resource: ResourceFacts
    situation: SituationFacts


def hard_gate_failures(inputs: PolicyInputs) -> list[Gate]:
    definition, target, resource, situation = (
        inputs.definition,
        inputs.target,
        inputs.resource,
        inputs.situation,
    )
    action = inputs.candidate.action_type
    checks: list[tuple[bool, Gate]] = [
        (definition is None, Gate.UNKNOWN_ACTION),
        (
            definition is not None and definition.base_class is PermissionClass.BLOCKED,
            Gate.BLOCKED_ACTION,
        ),
        (situation.global_kill_switch or target.halted, Gate.KILL_SWITCH),
        (not situation.execution_enabled, Gate.EXECUTION_DISABLED),
        (target.automation_level is AutomationLevel.OBSERVE_ONLY, Gate.OBSERVE_ONLY),
        (not resource.registered, Gate.UNREGISTERED_RESOURCE),
        (
            resource.registered and action not in resource.allowed_actions,
            Gate.NOT_ALLOWED_ON_RESOURCE,
        ),
        (resource.protected, Gate.PROTECTED_RESOURCE),
        (
            target.environment is Environment.PROD
            and (resource.profile is None or action not in resource.profile.enabled_actions),
            Gate.MISSING_SERVICE_PROFILE,
        ),
        (situation.evidence_age_seconds > FRESHNESS_LIMIT_SECONDS, Gate.STALE_EVIDENCE),
        (
            situation.action_in_flight_on_host or situation.prior_outcome_unknown,
            Gate.ACTION_IN_FLIGHT,
        ),
        (situation.previous_attempts_of_type > 0 or situation.cooldown_active, Gate.ATTEMPT_BUDGET),
        (
            definition is not None
            and definition.needs_recovery_asset
            and not resource.recovery_asset_available,
            Gate.MISSING_RECOVERY_ASSET,
        ),
        (not resource.headroom_ok, Gate.NO_HEADROOM),
        (situation.change_in_progress, Gate.CHANGE_IN_PROGRESS),
        (
            situation.is_security_incident
            and not (definition is not None and definition.containment),
            Gate.SECURITY_NON_CONTAINMENT,
        ),
        (not inputs.candidate.evidence_refs, Gate.NO_EVIDENCE),
    ]
    return [gate for failed, gate in checks if failed]


def uncertainty_level(situation: SituationFacts) -> int:
    confidence = situation.diagnosis_confidence
    if situation.prior_outcome_unknown or confidence < UNCERTAIN_CONFIDENCE_THRESHOLD:
        return 4
    if confidence < 0.8:
        return 2
    return 0


def impact_of(inputs: PolicyInputs, weights: ScoreWeights) -> Impact:
    definition = inputs.definition
    profile = inputs.resource.profile
    situation = inputs.situation
    if definition is None:
        return Impact(blast_radius=4, irreversibility=4, downtime=4, uncertainty=4, score=68)

    blast = definition.impact.blast_radius
    irreversibility = definition.impact.irreversibility
    downtime = definition.impact.downtime

    if profile is not None and definition.restart_class:
        if profile.serves_user_traffic:
            downtime = max(downtime, 3)
        if profile.redundancy is Redundancy.NONE:
            downtime = 4
    if profile is not None and profile.criticality is Criticality.CRITICAL:
        blast = max(blast, 2)
    if situation.maintenance_low_traffic:
        downtime = max(downtime - 1, 1)

    uncertainty = uncertainty_level(situation)
    score = (
        weights.blast_radius * blast
        + weights.irreversibility * irreversibility
        + weights.downtime * downtime
        + weights.uncertainty * uncertainty
    )
    if situation.slo_fast_burn:
        score += SLO_BURN_PENALTY
    return Impact(
        blast_radius=blast,
        irreversibility=irreversibility,
        downtime=downtime,
        uncertainty=uncertainty,
        score=score,
    )


def score_class(score: int, weights: ScoreWeights) -> PermissionClass:
    if score <= weights.safe_max:
        return PermissionClass.SAFE_ACTION
    return PermissionClass.REQUIRES_APPROVAL


def escalation_class(inputs: PolicyInputs) -> tuple[PermissionClass, list[str]]:
    situation = inputs.situation
    rules = [
        (situation.is_security_incident, "security_incident"),
        (situation.diagnosis_confidence < LOW_CONFIDENCE_THRESHOLD, "low_confidence"),
        (situation.suspected_injection, "suspected_injection"),
        (inputs.target.automation_level is AutomationLevel.APPROVAL_REQUIRED, "approval_required"),
        (
            inputs.candidate.action_type not in inputs.target.auto_actions,
            "not_on_auto_list",
        ),
    ]
    reasons = [reason for triggered, reason in rules if triggered]
    level = PermissionClass.REQUIRES_APPROVAL if reasons else PermissionClass.SAFE_ACTION
    return level, reasons


def evaluate_action(inputs: PolicyInputs, weights: ScoreWeights, policy_version: str) -> Decision:
    gates = hard_gate_failures(inputs)
    impact = impact_of(inputs, weights)
    base = inputs.definition.base_class if inputs.definition else PermissionClass.BLOCKED
    escalated, reasons = escalation_class(inputs)
    from_score = score_class(impact.score, weights)
    if inputs.target.environment is Environment.LAB:
        from_score = PermissionClass.SAFE_ACTION

    final = PermissionClass.strictest(base, escalated, from_score)
    if gates:
        final = PermissionClass.BLOCKED
    high_impact = impact.score > weights.approval_max

    return Decision(
        action_type=inputs.candidate.action_type,
        resource_id=inputs.candidate.resource_id,
        permission_class=final,
        eligible=not gates,
        auto_executable=(
            not gates
            and final is PermissionClass.SAFE_ACTION
            and not high_impact
            and inputs.target.automation_level is AutomationLevel.AUTO_SAFE
        ),
        high_impact=high_impact,
        gate_failures=gates,
        reasons=reasons,
        impact=impact,
        policy_version=policy_version,
    )


def evaluate_safely(inputs: PolicyInputs, weights: ScoreWeights, policy_version: str) -> Decision:
    try:
        return evaluate_action(inputs, weights, policy_version)
    except Exception as exc:
        return Decision(
            action_type=inputs.candidate.action_type,
            resource_id=inputs.candidate.resource_id,
            permission_class=PermissionClass.BLOCKED,
            eligible=False,
            auto_executable=False,
            high_impact=True,
            gate_failures=[],
            reasons=[f"policy_error:{type(exc).__name__}"],
            impact=Impact(blast_radius=4, irreversibility=4, downtime=4, uncertainty=4, score=68),
            policy_version=policy_version,
        )


def tool_call_allowed(permission: PermissionClass) -> tuple[bool, str]:
    if permission is PermissionClass.READ_ONLY:
        return True, "read_only"
    return False, "actions_are_never_called_through_the_tool_registry"
