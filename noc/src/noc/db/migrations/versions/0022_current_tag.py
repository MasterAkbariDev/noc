from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE targets SET tag = 'current' WHERE tag = 'panel host'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE targets SET tag = 'panel host' WHERE tag = 'current'"))
