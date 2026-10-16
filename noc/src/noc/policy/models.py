from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from noc_shared.permissions import PermissionClass


class Environment(StrEnum):
    LAB = "lab"
    PROD = "prod"


class AutomationLevel(StrEnum):
    OBSERVE_ONLY = "observe_only"
    APPROVAL_REQUIRED = "approval_required"
    AUTO_SAFE = "auto_safe"


class Redundancy(StrEnum):
    NONE = "none"
    REPLICATED = "replicated"


class Criticality(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


class ActionCheck(StrEnum):
    NONE = "none"
    SERVICE_ACTIVE = "service_active"
    SERVICE_INACTIVE = "service_inactive"
    DISK_FREE = "disk_free"
    CPU_RELIEVED = "cpu_relieved"
    MEMORY_RELIEVED = "memory_relieved"


class Gate(StrEnum):
    KILL_SWITCH = "kill_switch"
    EXECUTION_DISABLED = "execution_disabled"
    UNKNOWN_ACTION = "unknown_action"
    BLOCKED_ACTION = "blocked_action"
    OBSERVE_ONLY = "observe_only"
    NOT_ALLOWED_ON_RESOURCE = "not_allowed_on_resource"
    UNREGISTERED_RESOURCE = "unregistered_resource"
    PROTECTED_RESOURCE = "protected_resource"
    MISSING_SERVICE_PROFILE = "missing_service_profile"
    STALE_EVIDENCE = "stale_evidence"
    ACTION_IN_FLIGHT = "action_in_flight"
    ATTEMPT_BUDGET = "attempt_budget"
    MISSING_RECOVERY_ASSET = "missing_recovery_asset"
    NO_HEADROOM = "no_headroom"
    CHANGE_IN_PROGRESS = "change_in_progress"
    SECURITY_NON_CONTAINMENT = "security_non_containment"
    NO_EVIDENCE = "no_evidence"


class ImpactDefaults(BaseModel):
    model_config = ConfigDict(frozen=True)

    blast_radius: int = Field(ge=0, le=4)
    irreversibility: int = Field(ge=0, le=4)
    downtime: int = Field(ge=0, le=4)


class ActionDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    base_class: PermissionClass
    rung: int = Field(ge=0, le=5)
    restart_class: bool = False
    containment: bool = False
    needs_recovery_asset: bool = False
    check: ActionCheck = ActionCheck.NONE
    verify_timeout_seconds: int | None = Field(None, ge=30, le=1800)
    impact: ImpactDefaults

    @field_validator("base_class", mode="before")
    @classmethod
    def parse_class_name(cls, value: Any) -> Any:
        return PermissionClass[value] if isinstance(value, str) else value


class ServiceProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    criticality: Criticality = Criticality.NORMAL
    redundancy: Redundancy = Redundancy.NONE
    serves_user_traffic: bool = True
    enabled_actions: tuple[str, ...] = ()


class ScoreWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    blast_radius: int = 5
    irreversibility: int = 4
    downtime: int = 5
    uncertainty: int = 3
    safe_max: int = 12
    approval_max: int = 30


class ActionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_type: str
    resource_id: str
    params: dict[str, str | int] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()


class TargetFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: Environment
    automation_level: AutomationLevel
    auto_actions: tuple[str, ...] = ()
    halted: bool = False


class ResourceFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    registered: bool
    allowed_actions: tuple[str, ...] = ()
    protected: bool = False
    profile: ServiceProfile | None = None
    recovery_asset_available: bool = False
    headroom_ok: bool = True


class SituationFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    global_kill_switch: bool = False
    execution_enabled: bool = False
    evidence_age_seconds: float = 0.0
    action_in_flight_on_host: bool = False
    previous_attempts_of_type: int = 0
    cooldown_active: bool = False
    change_in_progress: bool = False
    is_security_incident: bool = False
    diagnosis_confidence: float = Field(ge=0.0, le=1.0)
    suspected_injection: bool = False
    prior_outcome_unknown: bool = False
    slo_fast_burn: bool = False
    maintenance_low_traffic: bool = False


class Impact(BaseModel):
    blast_radius: int
    irreversibility: int
    downtime: int
    uncertainty: int
    score: int


class Decision(BaseModel):
    action_type: str
    resource_id: str
    permission_class: PermissionClass
    eligible: bool
    auto_executable: bool
    high_impact: bool
    gate_failures: list[Gate]
    reasons: list[str]
    impact: Impact
    policy_version: str
