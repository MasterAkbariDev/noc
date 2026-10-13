from hypothesis import given
from hypothesis import strategies as st

from noc.config import PACKAGE_DIR
from noc.policy.engine import PolicyInputs, evaluate_action, evaluate_safely, tool_call_allowed
from noc.policy.loader import load_policy
from noc.policy.models import (
    ActionCandidate,
    AutomationLevel,
    Environment,
    Gate,
    Redundancy,
    ResourceFacts,
    ServiceProfile,
    SituationFacts,
    TargetFacts,
)
from noc_shared.permissions import PermissionClass

POLICY = load_policy(PACKAGE_DIR / "policy" / "default_policy.yaml")
RESTART = "restart_service"


def inputs(
    action: str = RESTART,
    environment: Environment = Environment.LAB,
    level: AutomationLevel = AutomationLevel.AUTO_SAFE,
    auto_actions: tuple[str, ...] = (RESTART,),
    resource: ResourceFacts | None = None,
    **situation: object,
) -> PolicyInputs:
    facts = {"execution_enabled": True, "diagnosis_confidence": 0.9, **situation}
    return PolicyInputs(
        candidate=ActionCandidate(
            action_type=action, resource_id="svc:demo-shop", evidence_refs=("T1",)
        ),
        definition=POLICY.actions.get(action),
        target=TargetFacts(
            environment=environment, automation_level=level, auto_actions=auto_actions
        ),
        resource=resource or ResourceFacts(registered=True, allowed_actions=(RESTART,)),
        situation=SituationFacts.model_validate(facts),
    )


def decide(policy_inputs: PolicyInputs):
    return evaluate_action(policy_inputs, POLICY.weights, POLICY.version)


def test_lab_restart_with_good_evidence_is_auto_safe() -> None:
    decision = decide(inputs())
    assert decision.eligible
    assert decision.permission_class is PermissionClass.SAFE_ACTION
    assert decision.auto_executable


def test_execution_disabled_blocks_everything() -> None:
    decision = decide(inputs(execution_enabled=False))
    assert Gate.EXECUTION_DISABLED in decision.gate_failures
    assert decision.permission_class is PermissionClass.BLOCKED
    assert not decision.auto_executable


def test_observe_only_target_never_acts() -> None:
    decision = decide(inputs(level=AutomationLevel.OBSERVE_ONLY))
    assert Gate.OBSERVE_ONLY in decision.gate_failures


def test_kill_switches_block() -> None:
    assert Gate.KILL_SWITCH in decide(inputs(global_kill_switch=True)).gate_failures


def test_unregistered_and_protected_resources_are_blocked() -> None:
    unregistered = decide(inputs(resource=ResourceFacts(registered=False)))
    protected = decide(
        inputs(resource=ResourceFacts(registered=True, allowed_actions=(RESTART,), protected=True))
    )
    assert Gate.UNREGISTERED_RESOURCE in unregistered.gate_failures
    assert Gate.PROTECTED_RESOURCE in protected.gate_failures


def test_prod_resource_without_profile_is_blocked() -> None:
    decision = decide(inputs(environment=Environment.PROD))
    assert Gate.MISSING_SERVICE_PROFILE in decision.gate_failures


def test_prod_restart_of_user_facing_singleton_needs_approval_and_is_high_impact() -> None:
    profile = ServiceProfile(redundancy=Redundancy.NONE, enabled_actions=(RESTART,))
    resource = ResourceFacts(registered=True, allowed_actions=(RESTART,), profile=profile)
    decision = decide(inputs(environment=Environment.PROD, resource=resource))
    assert decision.eligible
    assert decision.permission_class is PermissionClass.REQUIRES_APPROVAL
    assert decision.high_impact
    assert not decision.auto_executable


def test_blocked_catalog_action_stays_blocked() -> None:
    decision = decide(inputs(action="reboot_host", auto_actions=("reboot_host",)))
    assert Gate.BLOCKED_ACTION in decision.gate_failures


def test_unknown_action_is_blocked() -> None:
    assert Gate.UNKNOWN_ACTION in decide(inputs(action="run_command")).gate_failures


def test_policy_errors_fail_closed() -> None:
    broken = inputs()
    object.__setattr__(broken, "situation", None)
    decision = evaluate_safely(broken, POLICY.weights, POLICY.version)
    assert decision.permission_class is PermissionClass.BLOCKED
    assert decision.reasons[0].startswith("policy_error")


def test_only_read_only_tools_can_be_called_by_agents() -> None:
    assert tool_call_allowed(PermissionClass.READ_ONLY)[0]
    assert not tool_call_allowed(PermissionClass.SAFE_ACTION)[0]


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    injection=st.booleans(),
    security=st.booleans(),
    burn=st.booleans(),
)
def test_risk_signals_never_lower_the_class(
    confidence: float, injection: bool, security: bool, burn: bool
) -> None:
    calm = decide(inputs(diagnosis_confidence=1.0))
    risky = decide(
        inputs(
            diagnosis_confidence=confidence,
            suspected_injection=injection,
            is_security_incident=security,
            slo_fast_burn=burn,
        )
    )
    assert risky.permission_class >= calm.permission_class
    assert risky.impact.score >= calm.impact.score
