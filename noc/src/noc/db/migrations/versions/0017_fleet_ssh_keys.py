from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("sentinel_version", sa.String(length=32), nullable=True))
    op.create_table(
        "fleet_hosts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("ssh_user", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fleet_hosts")),
        sa.UniqueConstraint("name", name=op.f("uq_fleet_hosts_name")),
    )
    op.create_table(
        "ssh_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("from_pin", sa.String(length=255), nullable=True),
        sa.Column("forced_command", sa.String(length=32), nullable=True),
        sa.Column("has_passphrase", sa.Boolean(), nullable=False),
        sa.Column("rotation_days", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("replaces_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaces_id"], ["ssh_keys.id"], name=op.f("fk_ssh_keys_replaces_id_ssh_keys")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ssh_keys")),
        sa.UniqueConstraint("fingerprint", name=op.f("uq_ssh_keys_fingerprint")),
    )
    op.create_table(
        "ssh_key_installs",
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=False),
        sa.Column("sudo_scope_ok", sa.Boolean(), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marked_by", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["fleet_hosts.id"],
            name=op.f("fk_ssh_key_installs_host_id_fleet_hosts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["key_id"],
            ["ssh_keys.id"],
            name=op.f("fk_ssh_key_installs_key_id_ssh_keys"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key_id", "host_id", name=op.f("pk_ssh_key_installs")),
    )


def downgrade() -> None:
    op.drop_table("ssh_key_installs")
    op.drop_table("ssh_keys")
    op.drop_table("fleet_hosts")
    op.drop_column("targets", "sentinel_version")
