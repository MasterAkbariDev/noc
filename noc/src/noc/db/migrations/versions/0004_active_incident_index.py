from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = (
    "status IN ('AWAITING_APPROVAL', 'DIAGNOSED', 'INVESTIGATING', 'NEW', 'PLANNED', "
    "'REMEDIATING', 'VERIFYING')"
)
OPEN = "status NOT IN ('CLOSED', 'RESOLVED', 'SELF_RESOLVED')"


def upgrade() -> None:
    op.drop_index("uq_incidents_one_open_per_target", table_name="incidents")
    op.create_index(
        "uq_incidents_one_active_per_target",
        "incidents",
        ["target_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_incidents_one_active_per_target", table_name="incidents")
    op.create_index(
        "uq_incidents_one_open_per_target",
        "incidents",
        ["target_id"],
        unique=True,
        postgresql_where=sa.text(OPEN),
    )
