from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.UniqueConstraint("hash", name=op.f("uq_audit_log_hash")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_jobs_dedupe_key")),
    )
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_table(
        "llm_quota_usage",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=96), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("provider", "model", "day", name=op.f("pk_llm_quota_usage")),
    )
    op.create_table(
        "targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("sentinel_url", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("automation_level", sa.String(length=32), nullable=False),
        sa.Column("llm_data_policy", sa.String(length=32), nullable=False),
        sa.Column("hmac_key_id", sa.String(length=64), nullable=False),
        sa.Column("auto_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("halted", sa.Boolean(), nullable=False),
        sa.Column("last_inventory_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_targets")),
        sa.UniqueConstraint("name", name=op.f("uq_targets_name")),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnosed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_reason", sa.String(length=64), nullable=True),
        sa.Column("root_cause_code", sa.String(length=64), nullable=True),
        sa.Column("root_cause_summary", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.Column("tool_call_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_id"], ["targets.id"], name=op.f("fk_incidents_target_id_targets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)
    op.create_index(op.f("ix_incidents_target_id"), "incidents", ["target_id"], unique=False)
    op.create_index(
        "uq_incidents_one_open_per_target",
        "incidents",
        ["target_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('CLOSED', 'RESOLVED', 'SELF_RESOLVED')"),
    )
    op.create_table(
        "managed_resources",
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("allowed_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["targets.id"],
            name=op.f("fk_managed_resources_target_id_targets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("target_id", "resource_id", name=op.f("pk_managed_resources")),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("permission_class", sa.String(length=24), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("auto_executable", sa.Boolean(), nullable=False),
        sa.Column("gate_failures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("impact_score", sa.Integer(), nullable=False),
        sa.Column("high_impact", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(length=48), nullable=False),
        sa.Column("action_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_actions_incident_id_incidents")
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["targets.id"], name=op.f("fk_actions_target_id_targets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actions")),
        sa.UniqueConstraint("incident_id", "action_hash", name=op.f("uq_actions_incident_id")),
    )
    op.create_index(op.f("ix_actions_incident_id"), "actions", ["incident_id"], unique=False)
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_agent_runs_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_incident_id"), "agent_runs", ["incident_id"], unique=False)
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("alertname", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("annotations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("missed_polls", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_alert_events_incident_id_incidents")
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["targets.id"], name=op.f("fk_alert_events_target_id_targets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
    )
    op.create_index(
        op.f("ix_alert_events_incident_id"), "alert_events", ["incident_id"], unique=False
    )
    op.create_index(op.f("ix_alert_events_target_id"), "alert_events", ["target_id"], unique=False)
    op.create_index(
        "uq_alert_events_firing_fingerprint",
        "alert_events",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text("state = 'firing'"),
    )
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("primary_code", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("is_security_incident", sa.Boolean(), nullable=False),
        sa.Column("hypotheses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("needs_more_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ungrounded_findings", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_diagnoses_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnoses")),
    )
    op.create_index(op.f("ix_diagnoses_incident_id"), "diagnoses", ["incident_id"], unique=False)
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_strength", sa.String(length=16), nullable=False),
        sa.Column("counter_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("suspected_injection", sa.Boolean(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_findings_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
    )
    op.create_index(op.f("ix_findings_incident_id"), "findings", ["incident_id"], unique=False)
    op.create_table(
        "incident_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_incident_events_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_events")),
    )
    op.create_index(
        op.f("ix_incident_events_incident_id"), "incident_events", ["incident_id"], unique=False
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=96), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("wait_ms", sa.Integer(), nullable=False),
        sa.Column("fallback", sa.Boolean(), nullable=False),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("redactions", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_llm_calls_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index(op.f("ix_llm_calls_incident_id"), "llm_calls", ["incident_id"], unique=False)
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_reports_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint("incident_id", name=op.f("uq_reports_incident_id")),
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ref", sa.String(length=16), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("permission", sa.String(length=24), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("decision_reason", sa.String(length=255), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("injection_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_tool_calls_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_calls")),
    )
    op.create_index(op.f("ix_tool_calls_incident_id"), "tool_calls", ["incident_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_calls_incident_id"), table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_table("reports")
    op.drop_index(op.f("ix_llm_calls_incident_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_incident_events_incident_id"), table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index(op.f("ix_findings_incident_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_diagnoses_incident_id"), table_name="diagnoses")
    op.drop_table("diagnoses")
    op.drop_index(
        "uq_alert_events_firing_fingerprint",
        table_name="alert_events",
        postgresql_where=sa.text("state = 'firing'"),
    )
    op.drop_index(op.f("ix_alert_events_target_id"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_incident_id"), table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index(op.f("ix_agent_runs_incident_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_actions_incident_id"), table_name="actions")
    op.drop_table("actions")
    op.drop_table("managed_resources")
    op.drop_index(
        "uq_incidents_one_open_per_target",
        table_name="incidents",
        postgresql_where=sa.text("status NOT IN ('CLOSED', 'RESOLVED', 'SELF_RESOLVED')"),
    )
    op.drop_index(op.f("ix_incidents_target_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("targets")
    op.drop_table("llm_quota_usage")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("audit_log")
