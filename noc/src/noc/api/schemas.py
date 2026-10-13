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


class IncidentDetail(IncidentSummary):
    target: str
    trace_id: str
    events: list[EventView]
    findings: list[FindingView]
    actions: list[ActionView]
    report_markdown: str | None
