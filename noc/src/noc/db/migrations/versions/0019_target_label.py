from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("label", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "label")
