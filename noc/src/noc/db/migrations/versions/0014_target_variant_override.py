from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("variant_override", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "variant_override")
