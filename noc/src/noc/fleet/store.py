import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import FleetHost, SshKey, SshKeyInstall
from noc.fleet.commands import (
    CommandStep,
    HostSpec,
    check_address,
    check_host_name,
    check_ssh_user,
    noc_ip_from_pin,
    offboard_steps,
    paste_steps,
    revoke_steps,
    rotation_steps,
)
from noc.fleet.keys import (
    LIFETIME_RULES,
    KeyPurpose,
    KeyRefused,
    authorized_keys_line,
    check_label,
    check_rules,
    generate_keypair,
    normalize_pin,
    passphrase_secret_name,
    private_key_secret_name,
)
from noc.policy.models import Environment
from noc.secret_store import SecretStore

MIN_PORT = 1
MAX_PORT = 65535


@dataclass(frozen=True)
class NewHost:
    name: str
    address: str
    ssh_port: int
    ssh_user: str
    environment: Environment


@dataclass(frozen=True)
class NewKey:
    label: str
    purpose: KeyPurpose
    environment: Environment
    from_pin: str | None
    forced_command: str | None
    with_passphrase: bool
    rotation_days: int | None


@dataclass(frozen=True)
class Rotation:
    new_key: SshKey
    steps: list[CommandStep]


def host_spec(host: FleetHost) -> HostSpec:
    return HostSpec(host.name, host.address, host.ssh_user, host.environment)


def line_for(key: SshKey) -> str:
    return authorized_keys_line(
        key.id, key.public_key, key.from_pin, key.forced_command, key.expires_at
    )


def key_subject(key: SshKey) -> str:
    return f"ssh-key:{key.label}"


def host_subject(host: FleetHost) -> str:
    return f"host:{host.name}"


async def get_host(session: AsyncSession, host_id: uuid.UUID) -> FleetHost:
    host = await session.get(FleetHost, host_id)
    if host is None:
        raise LookupError("server not found")
    return host


async def get_active_key(session: AsyncSession, key_id: uuid.UUID) -> SshKey:
    key = await session.get(SshKey, key_id)
    if key is None or key.retired_at is not None:
        raise LookupError("key not found")
    return key


async def hosts_with_key(session: AsyncSession, key_id: uuid.UUID) -> list[FleetHost]:
    rows = await session.scalars(
        select(FleetHost)
        .join(SshKeyInstall, SshKeyInstall.host_id == FleetHost.id)
        .where(SshKeyInstall.key_id == key_id)
        .order_by(FleetHost.name)
    )
    return list(rows)


async def add_host(session: AsyncSession, new: NewHost, actor: str) -> FleetHost:
    name = check_host_name(new.name.strip())
    if not MIN_PORT <= new.ssh_port <= MAX_PORT:
        raise KeyRefused("the SSH port must be 1-65535")
    existing = await session.scalar(select(FleetHost).where(FleetHost.name == name))
    if existing is not None:
        raise KeyRefused(f"a server named {name} is already in the fleet")
    host = FleetHost(
        name=name,
        address=check_address(new.address),
        ssh_port=new.ssh_port,
        ssh_user=check_ssh_user(new.ssh_user.strip()),
        environment=new.environment.value,
        created_by=actor,
    )
    session.add(host)
    await session.flush()
    await append_audit(
        session,
        actor,
        "fleet_host_added",
        host_subject(host),
        {"address": host.address, "env": host.environment, "user": host.ssh_user},
    )
    return host


async def generate_key(
    session: AsyncSession, store: SecretStore, new: NewKey, actor: str
) -> SshKey:
    label = check_label(new.label)
    pin = normalize_pin(new.from_pin)
    rotation_days = new.rotation_days or LIFETIME_RULES[new.purpose].default_days
    check_rules(new.purpose, pin, new.forced_command, rotation_days)
    return await store_new_key(session, store, label, new, pin, rotation_days, actor, replaces=None)


async def store_new_key(
    session: AsyncSession,
    store: SecretStore,
    label: str,
    new: NewKey,
    pin: str | None,
    rotation_days: int,
    actor: str,
    replaces: SshKey | None,
) -> SshKey:
    generated = await asyncio.to_thread(generate_keypair, new.with_passphrase)
    now = utc_now()
    key = SshKey(
        label=label,
        purpose=new.purpose.value,
        environment=new.environment.value,
        public_key=generated.public_key,
        fingerprint=generated.fingerprint,
        from_pin=pin,
        forced_command=new.forced_command,
        has_passphrase=generated.passphrase is not None,
        rotation_days=rotation_days,
        created_at=now,
        expires_at=now + timedelta(days=rotation_days),
        created_by=actor,
        replaces_id=replaces.id if replaces else None,
    )
    session.add(key)
    await session.flush()
    await asyncio.to_thread(store.write, private_key_secret_name(key.id), generated.private_key)
    if generated.passphrase is not None:
        await asyncio.to_thread(store.write, passphrase_secret_name(key.id), generated.passphrase)
    await append_audit(
        session,
        actor,
        "ssh_key_generated",
        key_subject(key),
        {
            "purpose": key.purpose,
            "env": key.environment,
            "fingerprint": key.fingerprint,
            "from": pin,
            "days": rotation_days,
            "replaces": str(replaces.id) if replaces else None,
        },
    )
    return key


def check_key_fits_host(key: SshKey, host: FleetHost) -> None:
    if key.environment != host.environment:
        raise KeyRefused(
            f"a {key.environment} key cannot go on a {host.environment} server; "
            "production and lab keys are kept apart"
        )
    if not LIFETIME_RULES[KeyPurpose(key.purpose)].has_paste_command:
        raise KeyRefused("operator-shell keys are not installed from the panel yet")


async def paste_command(
    session: AsyncSession, host_id: uuid.UUID, key_id: uuid.UUID
) -> list[CommandStep]:
    host = await get_host(session, host_id)
    key = await get_active_key(session, key_id)
    check_key_fits_host(key, host)
    return paste_steps(host_spec(host), key.id, line_for(key), key.from_pin)


async def mark_installed(
    session: AsyncSession,
    host_id: uuid.UUID,
    key_id: uuid.UUID,
    sudo_scope_ok: bool,
    actor: str,
) -> SshKeyInstall:
    host = await get_host(session, host_id)
    key = await get_active_key(session, key_id)
    check_key_fits_host(key, host)
    install = await session.get(SshKeyInstall, (key.id, host.id))
    if install is None:
        install = SshKeyInstall(key_id=key.id, host_id=host.id, marked_by=actor)
        session.add(install)
    install.sudo_scope_ok = sudo_scope_ok
    install.marked_at = utc_now()
    install.marked_by = actor
    await session.flush()
    await append_audit(
        session,
        actor,
        "ssh_key_installed",
        host_subject(host),
        {"key": key.label, "fingerprint": key.fingerprint, "sudo_scope_ok": sudo_scope_ok},
    )
    return install


async def start_rotation(
    session: AsyncSession, store: SecretStore, key_id: uuid.UUID, actor: str
) -> Rotation:
    old = await get_active_key(session, key_id)
    pending = await session.scalar(
        select(SshKey).where(SshKey.replaces_id == old.id, SshKey.retired_at.is_(None))
    )
    if pending is not None:
        raise KeyRefused(f"a rotation of {old.label} is already waiting to be finished")
    template = NewKey(
        label=old.label,
        purpose=KeyPurpose(old.purpose),
        environment=Environment(old.environment),
        from_pin=old.from_pin,
        forced_command=old.forced_command,
        with_passphrase=old.has_passphrase,
        rotation_days=old.rotation_days,
    )
    new = await store_new_key(
        session, store, old.label, template, old.from_pin, old.rotation_days, actor, old
    )
    await append_audit(
        session, actor, "ssh_key_rotation_started", key_subject(old), {"new": new.fingerprint}
    )
    steps = [
        step
        for host in await hosts_with_key(session, old.id)
        for step in rotation_steps(host_spec(host), old.id, new.id, line_for(new))
    ]
    return Rotation(new, steps)


async def finish_rotation(
    session: AsyncSession, store: SecretStore, new_key_id: uuid.UUID, actor: str
) -> SshKey:
    new = await get_active_key(session, new_key_id)
    if new.replaces_id is None:
        raise KeyRefused("this key does not replace another key")
    old = await get_active_key(session, new.replaces_id)
    installs = list(
        await session.scalars(select(SshKeyInstall).where(SshKeyInstall.key_id == old.id))
    )
    for install in installs:
        if await session.get(SshKeyInstall, (new.id, install.host_id)) is None:
            session.add(
                SshKeyInstall(
                    key_id=new.id,
                    host_id=install.host_id,
                    sudo_scope_ok=install.sudo_scope_ok,
                    marked_at=utc_now(),
                    marked_by=actor,
                )
            )
    await session.flush()
    await retire(session, store, old, actor)
    await append_audit(
        session,
        actor,
        "ssh_key_rotated",
        key_subject(new),
        {"old": old.fingerprint, "new": new.fingerprint, "hosts": len(installs)},
    )
    return new


async def retire(session: AsyncSession, store: SecretStore, key: SshKey, actor: str) -> None:
    key.retired_at = utc_now()
    key.retired_by = actor
    await session.execute(delete(SshKeyInstall).where(SshKeyInstall.key_id == key.id))
    await session.flush()
    await asyncio.to_thread(store.delete, private_key_secret_name(key.id))
    await asyncio.to_thread(store.delete, passphrase_secret_name(key.id))


async def revoke_key(
    session: AsyncSession, store: SecretStore, key_id: uuid.UUID, actor: str
) -> list[CommandStep]:
    key = await get_active_key(session, key_id)
    hosts = await hosts_with_key(session, key.id)
    await retire(session, store, key, actor)
    await append_audit(
        session,
        actor,
        "ssh_key_revoked",
        key_subject(key),
        {"fingerprint": key.fingerprint, "hosts": [host.name for host in hosts]},
    )
    return [step for host in hosts for step in revoke_steps(host_spec(host), key.id)]


async def offboard_host(session: AsyncSession, host_id: uuid.UUID, actor: str) -> list[CommandStep]:
    host = await get_host(session, host_id)
    installed = list(
        await session.scalars(select(SshKeyInstall.key_id).where(SshKeyInstall.host_id == host.id))
    )
    pins = [key.from_pin for key_id in installed if (key := await session.get(SshKey, key_id))]
    steps = offboard_steps(host_spec(host), installed, noc_ip_from_pin(pins[0] if pins else None))
    await session.delete(host)
    await session.flush()
    await append_audit(
        session, actor, "fleet_host_offboarded", host_subject(host), {"keys": len(installed)}
    )
    return steps
