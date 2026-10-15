import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from noc.auth.roles import Role
from noc.reporting.operator_guide import GuideStep

ComponentStatus = Literal["ok", "degraded", "down", "unknown"]
Verdict = Literal["ok", "degraded", "down"]

MAX_TOTP_FIELD_LENGTH = 16
MAX_LOGIN_FIELD_LENGTH = 256


class IncidentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    severity: str
    target: str
    opened_at: datetime
    root_cause_code: str | None
    confidence: float | None
    escalation_reason: str | None


class EventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    type: str
    actor: str
    payload: dict[str, Any]
    text: str = ""


class FindingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    agent: str
    category: str
    severity: str
    summary: str
    evidence: list[dict[str, Any]]
    confidence: float
    suspected_injection: bool
    evidence_strength: str
    counter_evidence: list[str]
    grounded: bool


class ActionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_hash: str
    rung: int
    authorization: str | None
    approval_expires_at: datetime | None
    dispatched_at: datetime | None
    finished_at: datetime | None
    result_code: str | None
    action_type: str
    resource_id: str
    status: str
    permission_class: str
    eligible: bool
    gate_failures: list[str]
    gate_text: list[str] = []
    reasons: list[str]
    impact_score: int
    high_impact: bool
    auto_executable: bool
    policy_version: str


class HypothesisView(BaseModel):
    root_cause_code: str
    description: str
    confidence: float
    supporting_findings: list[str]
    contradicting_findings: list[str]
    affected_resource_id: str | None


class DiagnosisView(BaseModel):
    primary_code: str
    confidence: float
    is_security_incident: bool
    hypotheses: list[HypothesisView]
    needs_more_info: list[str]
    ungrounded_findings: int


class IncidentDetail(IncidentSummary):
    mode: str
    root_cause_summary: str | None
    resolution_note: str | None
    investigation_started_at: datetime | None
    diagnosed_at: datetime | None
    plan_at: datetime | None
    escalated_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    trace_id: str
    events: list[EventView]
    findings: list[FindingView]
    actions: list[ActionView]
    report_markdown: str | None
    diagnosis: DiagnosisView | None


class TargetResourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: str
    kind: str
    name: str


class TargetView(BaseModel):
    id: uuid.UUID
    name: str
    environment: str
    automation_level: str
    halted: bool
    last_inventory_at: datetime | None
    resources: list[TargetResourceView]


class AgentRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    rounds: int
    llm_calls: int
    tool_calls: int
    error: str | None


class ToolCallView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ref: str
    agent: str
    tool: str
    args: dict[str, Any]
    description: str = ""
    permission: str
    decision: str
    decision_reason: str | None
    ok: bool
    started_at: datetime
    duration_ms: int
    truncated: bool
    injection_flags: list[str]


class LlmCallView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    tier: str
    provider: str
    model: str
    mode: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    wait_ms: int
    fallback: bool
    finish_reason: str | None
    redactions: int
    error: str | None
    created_at: datetime


class IncidentTrace(BaseModel):
    agent_runs: list[AgentRunView]
    tool_calls: list[ToolCallView]
    llm_calls: list[LlmCallView]


class LlmModelUsage(BaseModel):
    tier: str
    model: str
    used_today: int
    daily_limit: int


class LlmKeyView(BaseModel):
    label: str
    provider: str
    tier: str = "free"
    state: str
    cooling_until: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    last_success_at: datetime | None
    models: list[LlmModelUsage]


class LlmStatus(BaseModel):
    mode: str
    keys: list[LlmKeyView]


KeyTierName = Literal["free", "paid"]


class LlmModelLimitView(BaseModel):
    tier: str
    model: str
    rpm: int
    rpd: int


class LlmProxyView(BaseModel):
    display: str | None
    source: Literal["env", "panel", "none"]


class LlmProviderView(BaseModel):
    name: str
    base_url: str
    proxy: LlmProxyView
    free_models: list[LlmModelLimitView]
    paid_models: list[LlmModelLimitView]


class LlmManagedKeyView(BaseModel):
    id: uuid.UUID | None
    label: str
    provider: str
    name: str | None
    tier: KeyTierName
    source: Literal["env", "panel"]
    last4: str
    created_at: datetime | None
    created_by: str | None


class LlmConfigView(BaseModel):
    mode: str
    secrets_persistent: bool
    providers: list[LlmProviderView]
    keys: list[LlmManagedKeyView]


class AddLlmKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(max_length=32)
    tier: KeyTierName = "free"
    name: str = Field(max_length=64)
    secret: str = Field(max_length=256)


class LlmCheckRequest(BaseModel):
    label: str = Field(max_length=64)


class SetProxyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=512)


class LlmCheckView(BaseModel):
    ok: bool
    latency_ms: int
    model: str | None
    detail: str


StepState = Literal["done", "current", "pending", "skipped", "failed"]


class StoryStep(BaseModel):
    key: str
    label: str
    state: StepState
    at: datetime | None


class StoryText(BaseModel):
    text: str
    technical: str | None


class StoryEvidence(BaseModel):
    source: str
    quote: str


class StoryPoint(BaseModel):
    text: str
    agent: str
    label: str
    evidence: list[StoryEvidence]
    grounded: bool


class StoryFound(BaseModel):
    text: str
    root_cause_code: str | None
    root_cause_label: str | None
    confidence: float | None
    points: list[StoryPoint]


class StoryAction(BaseModel):
    action: str
    action_label: str
    verdict: str
    verdict_label: str
    reasons: list[str]
    technical: list[str]


class StoryDid(BaseModel):
    text: str
    considered: list[StoryAction]


class StoryAdvice(BaseModel):
    text: str
    steps: list[GuideStep]


class IncidentStory(BaseModel):
    id: uuid.UUID
    title: str
    target: str
    severity: str
    status: str
    status_label: str
    headline: str
    steps: list[StoryStep]
    what_happened: StoryText
    what_we_found: StoryFound
    what_we_did: StoryDid
    what_you_should_do: StoryAdvice


class ComponentHealth(BaseModel):
    key: str
    label: str
    status: ComponentStatus
    summary: str
    details: dict[str, str]
    since: datetime | None


class StuckIncident(BaseModel):
    id: uuid.UUID
    title: str
    target: str
    status: str
    since: datetime
    job_status: str | None
    job_attempts: int | None
    job_last_error: str | None


class SystemHealth(BaseModel):
    verdict: Verdict
    checked_at: datetime
    components: list[ComponentHealth]
    stuck_incidents: list[StuckIncident]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    comment: str | None = Field(default=None, max_length=500)
    totp: str | None = Field(default=None, max_length=MAX_TOTP_FIELD_LENGTH)


class ApprovalView(BaseModel):
    approval_id: uuid.UUID
    incident_status: str


ServerStatus = Literal["up", "down", "unknown"]


class ServerMetrics(BaseModel):
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    disk_mount: str | None


class ServerSummary(BaseModel):
    id: uuid.UUID
    name: str
    environment: str
    automation_level: str
    automation_label: str
    halted: bool
    status: ServerStatus
    last_scrape_at: datetime | None
    metrics: ServerMetrics | None
    open_incidents: int
    worst_severity: str | None
    headline: str


class ServiceState(BaseModel):
    resource_id: str
    name: str
    up: bool | None


class ServerDetail(ServerSummary):
    last_inventory_at: datetime | None
    resources: list[TargetResourceView]
    services: list[ServiceState]
    recent_incidents: list[IncidentSummary]


class ActivityEntry(BaseModel):
    id: int
    ts: datetime
    actor: str
    action: str
    action_label: str
    subject: str
    summary: str
    payload: dict[str, Any]


class ActivityPage(BaseModel):
    items: list[ActivityEntry]
    next_before_id: int | None


class ChainVerification(BaseModel):
    ok: bool
    broken_at: int | None


class LoginRequest(BaseModel):
    username: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    totp: str | None = Field(default=None, max_length=MAX_TOTP_FIELD_LENGTH)


class TotpSetupRequest(BaseModel):
    current_password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)


class TotpSetupView(BaseModel):
    secret: str
    uri: str


class TotpEnableRequest(BaseModel):
    code: str = Field(max_length=MAX_TOTP_FIELD_LENGTH)


class TotpDisableRequest(BaseModel):
    current_password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    code: str = Field(max_length=MAX_TOTP_FIELD_LENGTH)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    new_password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)


class MeView(BaseModel):
    username: str
    role: Role
    via: Literal["session", "token"]
    totp_enabled: bool = False
    totp_required: bool = False


OverviewLevel = Literal["ok", "working", "attention", "degraded", "down"]
ActivityKind = Literal["incident", "audit"]


class OverviewVerdict(BaseModel):
    level: OverviewLevel
    sentence: str


class Kpis(BaseModel):
    open_incidents: int
    needs_you: int
    servers_up: int
    servers_total: int
    llm_keys_ok: int
    llm_keys_total: int


class AttentionItem(BaseModel):
    incident_id: uuid.UUID
    title: str
    target: str
    severity: str
    status: str
    status_label: str
    since: datetime
    summary: str
    advice: str


class ActivityItem(BaseModel):
    ts: datetime
    kind: ActivityKind
    text: str
    incident_id: uuid.UUID | None
    actor: str


class Overview(BaseModel):
    verdict: OverviewVerdict
    kpis: Kpis
    needs_attention: list[AttentionItem]
    activity: list[ActivityItem]
    servers: list[ServerSummary]


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: Role
    disabled: bool
    created_at: datetime
    last_login_at: datetime | None


class CreateUserRequest(BaseModel):
    username: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
    role: Role


class SetRoleRequest(BaseModel):
    role: Role


class SetUserPasswordRequest(BaseModel):
    new_password: str = Field(max_length=MAX_LOGIN_FIELD_LENGTH)
