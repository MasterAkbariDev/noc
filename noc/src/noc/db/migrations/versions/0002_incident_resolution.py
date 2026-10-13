from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column(
        "incidents",
        sa.Column("corrected_root_cause_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "corrected_root_cause_code")
    op.drop_column("incidents", "resolution_note")
