import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


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

    action_type: str
    resource_id: str
    status: str
    permission_class: str
    eligible: bool
    gate_failures: list[str]
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
