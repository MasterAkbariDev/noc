from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_poll_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_error", sa.Text(), nullable=True),
        sa.Column("last_poll_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
