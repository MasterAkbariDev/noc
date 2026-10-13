import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from noc.db.base import Base, CreatedAt, new_id, utc_now
from noc.domain.incident_status import CLOSED_STATUSES

Json = dict[str, Any]

OPEN_INCIDENT_PREDICATE = text(
    "status NOT IN (" + ", ".join(f"'{status.value}'" for status in sorted(CLOSED_STATUSES)) + ")"
)


class Target(CreatedAt, Base):
    __tablename__ = "targets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    sentinel_url: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(8))
    automation_level: Mapped[str] = mapped_column(String(32), default="observe_only")
    llm_data_policy: Mapped[str] = mapped_column(String(32), default="redacted")
    hmac_key_id: Mapped[str] = mapped_column(String(64))
    auto_actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    halted: Mapped[bool] = mapped_column(default=False)
    last_inventory_at: Mapped[datetime | None]

    resources: Mapped[list["ManagedResourceRow"]] = relationship(
        back_populates="target", cascade="all, delete-orphan"
    )


class ManagedResourceRow(Base):
    __tablename__ = "managed_resources"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    allowed_actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    profile: Mapped[Json | None] = mapped_column(JSONB)

    target: Mapped[Target] = relationship(back_populates="resources")


class Incident(CreatedAt, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "uq_incidents_one_open_per_target",
            "target_id",
            unique=True,
            postgresql_where=OPEN_INCIDENT_PREDICATE,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("targets.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    trace_id: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), default="single")
    opened_at: Mapped[datetime] = mapped_column(default=utc_now)
    investigation_started_at: Mapped[datetime | None]
    diagnosed_at: Mapped[datetime | None]
    plan_at: Mapped[datetime | None]
    escalated_at: Mapped[datetime | None]
    resolved_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    escalation_reason: Mapped[str | None] = mapped_column(String(64))
    root_cause_code: Mapped[str | None] = mapped_column(String(64))
    root_cause_summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None]
    tool_call_seq: Mapped[int] = mapped_column(Integer, default=0)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    corrected_root_cause_code: Mapped[str | None] = mapped_column(String(64))

    target: Mapped[Target] = relationship()


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index(
            "uq_alert_events_firing_fingerprint",
            "fingerprint",
            unique=True,
            postgresql_where=text("state = 'firing'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("targets.id"), index=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    alertname: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    labels: Mapped[dict[str, str]] = mapped_column(JSONB)
    annotations: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    value: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    starts_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]
    missed_polls: Mapped[int] = mapped_column(Integer, default=0)


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    ts: Mapped[datetime] = mapped_column(default=utc_now)
    type: Mapped[str] = mapped_column(String(48))
    actor: Mapped[str] = mapped_column(String(64))
    payload: Mapped[Json] = mapped_column(JSONB, default=dict)


class Job(CreatedAt, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(48))
    payload: Mapped[Json] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(default=utc_now)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    ended_at: Mapped[datetime | None]
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    ref: Mapped[str] = mapped_column(String(16))
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[Json] = mapped_column(JSONB)
    permission: Mapped[str] = mapped_column(String(24))
    decision: Mapped[str] = mapped_column(String(24))
    decision_reason: Mapped[str | None] = mapped_column(String(255))
    ok: Mapped[bool]
    started_at: Mapped[datetime]
    duration_ms: Mapped[int] = mapped_column(Integer)
    result: Mapped[Json | None] = mapped_column(JSONB)
    result_text: Mapped[str] = mapped_column(Text, default="")
    result_sha256: Mapped[str] = mapped_column(String(64))
    truncated: Mapped[bool] = mapped_column(default=False)
    injection_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)


class LlmCall(CreatedAt, Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    tier: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(96))
    mode: Mapped[str] = mapped_column(String(16))
    request_hash: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    wait_ms: Mapped[int] = mapped_column(Integer, default=0)
    fallback: Mapped[bool] = mapped_column(default=False)
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    redactions: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class LlmQuotaUsage(Base):
    __tablename__ = "llm_quota_usage"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(96), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)


class FindingRow(CreatedAt, Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[Json]] = mapped_column(JSONB)
    evidence_strength: Mapped[str] = mapped_column(String(16))
    counter_evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float]
    suspected_injection: Mapped[bool] = mapped_column(default=False)
    grounded: Mapped[bool] = mapped_column(default=False)


class DiagnosisRow(CreatedAt, Base):
    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    primary_code: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float]
    is_security_incident: Mapped[bool] = mapped_column(default=False)
    hypotheses: Mapped[list[Json]] = mapped_column(JSONB)
    needs_more_info: Mapped[list[str]] = mapped_column(JSONB, default=list)
    ungrounded_findings: Mapped[int] = mapped_column(Integer, default=0)


class ActionRow(CreatedAt, Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("incident_id", "action_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("targets.id"))
    action_type: Mapped[str] = mapped_column(String(48))
    resource_id: Mapped[str] = mapped_column(String(160))
    params: Mapped[Json] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(24))
    permission_class: Mapped[str] = mapped_column(String(24))
    eligible: Mapped[bool]
    auto_executable: Mapped[bool]
    gate_failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    impact_score: Mapped[int] = mapped_column(Integer)
    high_impact: Mapped[bool] = mapped_column(default=False)
    policy_version: Mapped[str] = mapped_column(String(48))
    action_hash: Mapped[str] = mapped_column(String(64))


class Report(CreatedAt, Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), unique=True)
    markdown: Mapped[str] = mapped_column(Text)


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utc_now)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(160))
    payload: Mapped[Json] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    scenario: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("targets.id"), index=True)
    resource_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), index=True)
    ground_truth: Mapped[Json] = mapped_column(JSONB)
    injected_at: Mapped[datetime]
    detected_at: Mapped[datetime | None]
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    final_status: Mapped[str | None] = mapped_column(String(32))
    detection_seconds: Mapped[float | None]
    root_cause_match: Mapped[bool | None]
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
