from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_incident_events_ts"), "incident_events", ["ts"], unique=False)
    op.create_index(op.f("ix_audit_log_ts"), "audit_log", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_log_ts"), table_name="audit_log")
    op.drop_index(op.f("ix_incident_events_ts"), table_name="incident_events")
