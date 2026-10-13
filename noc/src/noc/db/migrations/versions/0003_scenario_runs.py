from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ground_truth", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("injected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("final_status", sa.String(length=32), nullable=True),
        sa.Column("detection_seconds", sa.Double(), nullable=True),
        sa.Column("root_cause_match", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_scenario_runs_incident_id_incidents")
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["targets.id"], name=op.f("fk_scenario_runs_target_id_targets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_runs")),
    )
    op.create_index(op.f("ix_scenario_runs_status"), "scenario_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_scenario_runs_target_id"), "scenario_runs", ["target_id"], unique=False
    )
    op.create_index(
        op.f("ix_scenario_runs_incident_id"), "scenario_runs", ["incident_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scenario_runs_incident_id"), table_name="scenario_runs")
    op.drop_index(op.f("ix_scenario_runs_target_id"), table_name="scenario_runs")
    op.drop_index(op.f("ix_scenario_runs_status"), table_name="scenario_runs")
    op.drop_table("scenario_runs")
