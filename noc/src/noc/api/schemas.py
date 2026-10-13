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
