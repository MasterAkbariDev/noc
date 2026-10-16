import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Final, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.api.prometheus import PrometheusReader, ScrapeTarget
from noc.api.schemas import (
    AddFleetHostRequest,
    CommandStepView,
    CommandsView,
    EnvironmentName,
    FleetRowView,
    FleetView,
    ForcedCommandView,
    GenerateSshKeyRequest,
    InstalledKeyView,
    MarkInstalledRequest,
    PasteCommandRequest,
    RotationView,
    SshKeyPurposeName,
    SshKeyRuleView,
    SshKeyState,
    SshKeyView,
    TotpConfirmation,
)
from noc.api.servers import reading_or_none, scrape_status
from noc.auth.approval_factor import SecondFactorRefused, confirm_second_factor
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import FleetHost, SshKey, SshKeyInstall, Target
from noc.fleet.commands import CommandStep
from noc.fleet.keys import FORCED_COMMANDS, LIFETIME_RULES, KeyPurpose, KeyRefused, rotation_due_at
from noc.fleet.store import (
    NewHost,
    NewKey,
    add_host,
    finish_rotation,
    generate_key,
    mark_installed,
    offboard_host,
    paste_command,
    revoke_key,
    start_rotation,
)
from noc.policy.models import Environment
from noc.reporting import plain_language as words
from noc.secret_store import SecretStore

router = APIRouter(prefix="/api/fleet", tags=["fleet"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]

NODE_JOB: Final = "node"
SENTINEL_JOB: Final = "sentinel"
JOB_LABEL: Final = "job"
RETIRED_SHOWN_DAYS: Final = 30
NEEDS_PERSON: Final = "SSH key and fleet changes need a signed-in person, not an API token"
NEEDS_ENROLMENT: Final = "turn on two-factor authentication in Settings before changing SSH keys"
BOOTSTRAP_LEFT_OVER: Final = (
    "The helper is up, so the bootstrap key is no longer needed: revoke it."
)
NO_SSH_DETAILS: Final = "Monitored, but no SSH details yet: add it to the fleet to manage keys."
SUDO_TOO_WIDE: Final = "The ops user had sudo rights when the key was installed: check sudoers."
KEY_EXPIRED: Final = "A key on this server has expired: rotate it or install a new one."


def secret_store(settings: AppSettings) -> SecretStore:
    return SecretStore(settings.secrets_dir)


Store = Annotated[SecretStore, Depends(secret_store)]


async def require_fresh_code(
    session: AsyncSession, admin: Principal, code: str | None, subject: str
) -> None:
    if admin.user_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NEEDS_PERSON)
    if not admin.totp_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NEEDS_ENROLMENT)
    try:
        await confirm_second_factor(session, admin.user_id, code, subject)
    except SecondFactorRefused as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error


def refused(error: KeyRefused) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def not_found(error: LookupError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(error.args[0]))


def key_state(key: SshKey, replaced: set[uuid.UUID], now: datetime) -> SshKeyState:
    if key.retired_at is not None:
        return "retired"
    if key.expires_at <= now:
        return "expired"
    if key.id in replaced:
        return "rotating"
    if rotation_due_at(key.created_at, key.expires_at) <= now:
        return "rotate_soon"
    return "active"


def key_view(key: SshKey, replaced: set[uuid.UUID], hosts: list[str], now: datetime) -> SshKeyView:
    return SshKeyView(
        id=key.id,
        label=key.label,
        purpose=cast(SshKeyPurposeName, key.purpose),
        environment=cast(EnvironmentName, key.environment),
        public_key=key.public_key,
        fingerprint=key.fingerprint,
        from_pin=key.from_pin,
        forced_command=key.forced_command,
        has_passphrase=key.has_passphrase,
        rotation_days=key.rotation_days,
        created_at=key.created_at,
        created_by=key.created_by,
        expires_at=key.expires_at,
        rotation_due_at=rotation_due_at(key.created_at, key.expires_at),
        state=key_state(key, replaced, now),
        replaces_id=key.replaces_id,
        retired_at=key.retired_at,
        hosts=hosts,
    )


def installed_view(
    install: SshKeyInstall, key: SshKey, replaced: set[uuid.UUID], now: datetime
) -> InstalledKeyView:
    return InstalledKeyView(
        key_id=key.id,
        label=key.label,
        purpose=cast(SshKeyPurposeName, key.purpose),
        fingerprint=key.fingerprint,
        installed_at=install.marked_at,
        expires_at=key.expires_at,
        rotation_due_at=rotation_due_at(key.created_at, key.expires_at),
        state=key_state(key, replaced, now),
        sudo_scope_ok=install.sudo_scope_ok,
    )


def job_up(scrape_targets: list[ScrapeTarget] | None, name: str, job: str) -> bool | None:
    if scrape_targets is None:
        return None
    own_job = [item for item in scrape_targets if item.labels.get(JOB_LABEL) == job]
    state, _ = scrape_status(own_job, name)
    return None if state == "unknown" else state == "up"


def row_notes(
    host: FleetHost | None, keys: list[InstalledKeyView], helper_up: bool | None
) -> list[str]:
    if host is None:
        return [NO_SSH_DETAILS]
    notes: list[str] = []
    if helper_up and any(key.purpose == KeyPurpose.BOOTSTRAP.value for key in keys):
        notes.append(BOOTSTRAP_LEFT_OVER)
    if any(not key.sudo_scope_ok for key in keys):
        notes.append(SUDO_TOO_WIDE)
    if any(key.state == "expired" for key in keys):
        notes.append(KEY_EXPIRED)
    return notes


def fleet_row(
    name: str,
    host: FleetHost | None,
    target: Target | None,
    keys: list[InstalledKeyView],
    scrape_targets: list[ScrapeTarget] | None,
) -> FleetRowView:
    helper_up = job_up(scrape_targets, name, SENTINEL_JOB) if target else None
    environment = host.environment if host else target.environment if target else "prod"
    return FleetRowView(
        host_id=host.id if host else None,
        target_id=target.id if target else None,
        name=name,
        address=host.address if host else target.address if target else "",
        ssh_port=host.ssh_port if host else None,
        ssh_user=host.ssh_user if host else None,
        environment=cast(EnvironmentName, environment),
        reachable=job_up(scrape_targets, name, NODE_JOB) if target else None,
        helper_up=helper_up,
        helper_version=target.sentinel_version if target else None,
        keys=keys,
        automation_level=target.automation_level if target else None,
        automation_label=(
            words.text_for(words.AUTOMATION_LABELS, target.automation_level) if target else None
        ),
        notes=row_notes(host, keys, helper_up),
    )


async def fleet_view(
    session: AsyncSession, store: SecretStore, reader: PrometheusReader
) -> FleetView:
    now = utc_now()
    hosts = {host.name: host for host in await session.scalars(select(FleetHost))}
    targets = {target.name: target for target in await session.scalars(select(Target))}
    shown_since = now - timedelta(days=RETIRED_SHOWN_DAYS)
    keys = list(
        await session.scalars(
            select(SshKey)
            .where(or_(SshKey.retired_at.is_(None), SshKey.retired_at > shown_since))
            .order_by(SshKey.created_at.desc())
        )
    )
    by_id = {key.id: key for key in keys}
    replaced = {key.replaces_id for key in keys if key.replaces_id and key.retired_at is None}
    host_names = {host.id: host.name for host in hosts.values()}
    installs_by_host: defaultdict[uuid.UUID, list[InstalledKeyView]] = defaultdict(list)
    hosts_by_key: defaultdict[uuid.UUID, list[str]] = defaultdict(list)
    for install in await session.scalars(select(SshKeyInstall)):
        key = by_id.get(install.key_id)
        if key is None:
            continue
        installs_by_host[install.host_id].append(installed_view(install, key, replaced, now))
        hosts_by_key[key.id].append(host_names[install.host_id])
    scrape_targets = await reading_or_none(reader.targets())
    rows = [
        fleet_row(
            name,
            hosts.get(name),
            targets.get(name),
            installs_by_host[hosts[name].id] if name in hosts else [],
            scrape_targets,
        )
        for name in sorted(hosts.keys() | targets.keys())
    ]
    return FleetView(
        secrets_persistent=await asyncio.to_thread(store.is_persistent),
        metrics_available=scrape_targets is not None,
        hosts=rows,
        keys=[key_view(key, replaced, sorted(hosts_by_key[key.id]), now) for key in keys],
        rules=[
            SshKeyRuleView(
                purpose=purpose.value,
                default_days=rule.default_days,
                min_days=rule.min_days,
                max_days=rule.max_days,
                needs_pin=rule.needs_pin,
                allows_forced_command=rule.allows_forced_command,
                has_paste_command=rule.has_paste_command,
            )
            for purpose, rule in LIFETIME_RULES.items()
        ],
        forced_commands=[
            ForcedCommandView(name=name, command=command)
            for name, command in FORCED_COMMANDS.items()
        ],
    )


def commands_view(steps: list[CommandStep]) -> CommandsView:
    return CommandsView(steps=[step_view(step) for step in steps])


def step_view(step: CommandStep) -> CommandStepView:
    return CommandStepView(title=step.title, where=step.where, command=step.command)


async def single_key_view(session: AsyncSession, key: SshKey) -> SshKeyView:
    hosts = await session.scalars(
        select(FleetHost.name)
        .join(SshKeyInstall, SshKeyInstall.host_id == FleetHost.id)
        .where(SshKeyInstall.key_id == key.id)
        .order_by(FleetHost.name)
    )
    return key_view(key, set(), list(hosts), utc_now())


def prometheus(request: Request) -> PrometheusReader:
    reader: PrometheusReader = request.app.state.prometheus
    return reader


Reader = Annotated[PrometheusReader, Depends(prometheus)]


@router.get("")
async def get_fleet(
    admin: AdminPrincipal, session: Session, store: Store, reader: Reader
) -> FleetView:
    return await fleet_view(session, store, reader)


@router.post("/hosts", status_code=status.HTTP_204_NO_CONTENT)
async def create_host(body: AddFleetHostRequest, admin: AdminPrincipal, session: Session) -> None:
    await require_fresh_code(session, admin, body.totp, f"host:{body.name}")
    new = NewHost(
        body.name, body.address, body.ssh_port, body.ssh_user, Environment(body.environment)
    )
    try:
        await add_host(session, new, admin.username)
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()


@router.post("/hosts/{host_id}/offboard")
async def offboard(
    host_id: uuid.UUID, body: TotpConfirmation, admin: AdminPrincipal, session: Session
) -> CommandsView:
    await require_fresh_code(session, admin, body.totp, f"host:{host_id}")
    try:
        steps = await offboard_host(session, host_id, admin.username)
    except LookupError as error:
        raise not_found(error) from error
    await session.commit()
    return commands_view(steps)


@router.post("/hosts/{host_id}/paste-command")
async def get_paste_command(
    host_id: uuid.UUID, body: PasteCommandRequest, admin: AdminPrincipal, session: Session
) -> CommandsView:
    try:
        steps = await paste_command(session, host_id, body.key_id)
    except LookupError as error:
        raise not_found(error) from error
    except KeyRefused as error:
        raise refused(error) from error
    return commands_view(steps)


@router.post("/hosts/{host_id}/installed", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_installed(
    host_id: uuid.UUID, body: MarkInstalledRequest, admin: AdminPrincipal, session: Session
) -> None:
    await require_fresh_code(session, admin, body.totp, f"host:{host_id}")
    try:
        await mark_installed(session, host_id, body.key_id, body.sudo_scope_ok, admin.username)
    except LookupError as error:
        raise not_found(error) from error
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()


@router.post("/keys")
async def create_key(
    body: GenerateSshKeyRequest, admin: AdminPrincipal, session: Session, store: Store
) -> SshKeyView:
    await require_fresh_code(session, admin, body.totp, f"ssh-key:{body.label}")
    new = NewKey(
        label=body.label,
        purpose=KeyPurpose(body.purpose),
        environment=Environment(body.environment),
        from_pin=body.from_pin,
        forced_command=body.forced_command or None,
        with_passphrase=body.with_passphrase,
        rotation_days=body.rotation_days,
    )
    try:
        key = await generate_key(session, store, new, admin.username)
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return await single_key_view(session, key)


@router.post("/keys/{key_id}/rotate")
async def rotate_key(
    key_id: uuid.UUID,
    body: TotpConfirmation,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> RotationView:
    await require_fresh_code(session, admin, body.totp, f"ssh-key:{key_id}")
    try:
        rotation = await start_rotation(session, store, key_id, admin.username)
    except LookupError as error:
        raise not_found(error) from error
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return RotationView(
        new_key=await single_key_view(session, rotation.new_key),
        steps=[step_view(step) for step in rotation.steps],
    )


@router.post("/keys/{key_id}/finish-rotation")
async def finish_key_rotation(
    key_id: uuid.UUID,
    body: TotpConfirmation,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> SshKeyView:
    await require_fresh_code(session, admin, body.totp, f"ssh-key:{key_id}")
    try:
        key = await finish_rotation(session, store, key_id, admin.username)
    except LookupError as error:
        raise not_found(error) from error
    except KeyRefused as error:
        raise refused(error) from error
    await session.commit()
    return await single_key_view(session, key)


@router.post("/keys/{key_id}/revoke")
async def revoke(
    key_id: uuid.UUID,
    body: TotpConfirmation,
    admin: AdminPrincipal,
    session: Session,
    store: Store,
) -> CommandsView:
    await require_fresh_code(session, admin, body.totp, f"ssh-key:{key_id}")
    try:
        steps = await revoke_key(session, store, key_id, admin.username)
    except LookupError as error:
        raise not_found(error) from error
    await session.commit()
    return commands_view(steps)
