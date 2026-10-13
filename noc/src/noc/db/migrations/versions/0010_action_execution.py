from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("actions", sa.Column("rung", sa.Integer(), server_default="0", nullable=False))
    op.add_column("actions", sa.Column("attempt", sa.Integer(), server_default="1", nullable=False))
    op.add_column("actions", sa.Column("attempt_id", sa.Uuid(), nullable=True))
    op.add_column("actions", sa.Column("authorization", sa.String(length=96), nullable=True))
    op.add_column("actions", sa.Column("approval_expires_at", TIMESTAMP, nullable=True))
    op.add_column("actions", sa.Column("dispatched_at", TIMESTAMP, nullable=True))
    op.add_column("actions", sa.Column("finished_at", TIMESTAMP, nullable=True))
    op.add_column("actions", sa.Column("result_code", sa.String(length=48), nullable=True))
    op.add_column(
        "actions",
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("action_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"], ["actions.id"], name=op.f("fk_approvals_action_id_actions")
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], name=op.f("fk_approvals_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.UniqueConstraint("action_id", name=op.f("uq_approvals_action_id")),
    )
    op.create_index(op.f("ix_approvals_incident_id"), "approvals", ["incident_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_approvals_incident_id"), table_name="approvals")
    op.drop_table("approvals")
    for column in (
        "result",
        "result_code",
        "finished_at",
        "dispatched_at",
        "approval_expires_at",
        "authorization",
        "attempt_id",
        "attempt",
        "rung",
    ):
        op.drop_column("actions", column)
