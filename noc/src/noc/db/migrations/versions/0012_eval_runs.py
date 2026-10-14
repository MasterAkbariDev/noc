from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan", sa.String(length=64), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("variant", sa.String(length=16), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("scenario_run_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["scenario_run_id"],
            ["scenario_runs.id"],
            name=op.f("fk_eval_runs_scenario_run_id_scenario_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
        sa.UniqueConstraint("plan", "scenario", "variant", "repetition", name="uq_eval_runs_cell"),
    )
    op.create_index(op.f("ix_eval_runs_plan"), "eval_runs", ["plan"], unique=False)
    op.create_index(op.f("ix_eval_runs_status"), "eval_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_runs_status"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_plan"), table_name="eval_runs")
    op.drop_table("eval_runs")
