import asyncio
import os
import re
import secrets
import sys
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from noc.api.app import create_app
from noc.audit.anchor import (
    AnchorError,
    anchor_filename,
    check_anchors,
    create_anchor,
    load_anchors,
    read_key,
)
from noc.audit.chain import append_audit, verify_chain
from noc.auth.roles import Role
from noc.auth.totp import provisioning_uri
from noc.auth.users import (
    clear_totp,
    create_user,
    delete_user,
    enroll_totp,
    list_users,
    require_user,
    reset_password,
    set_disabled,
    set_role,
    unlock_user,
)
from noc.config import PACKAGE_DIR, Settings, get_settings
from noc.db.base import utc_now
from noc.db.models import ActionRow, EvalRun, Incident, Report, ScenarioRun, Target, User
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.file_sd import render_file_sd
from noc.doctor import (
    CheckResult,
    check_database,
    check_external_heartbeat,
    check_llm,
    check_policy,
    check_prometheus,
    check_secrets_dir,
    check_targets,
    check_variant_overrides,
)
from noc.domain.incident_status import InvalidTransition
from noc.domain.variants import VARIANTS, parse_variant
from noc.evaluation.loop import EvalLoop, LoopSettings
from noc.evaluation.metrics import summarize_all, to_csv
from noc.evaluation.plan import load_plan
from noc.evaluation.store import load_records, materialize, status_counts
from noc.logging import configure_logging
from noc.policy.loader import load_policy
from noc.policy.models import AutomationLevel, Environment
from noc.scenarios.chaos_client import ChaosError, build_chaos_client
from noc.scenarios.definitions import ScenarioDefinition, injection_summary, load_scenarios
from noc.scenarios.runner import PreconditionFailed, RunOutcome, ScenarioRunner, run_resource
from noc.store.incidents import IncidentResolution, close_incident
from noc.store.remediation import ApprovalConflict, ApprovalDecision, record_approval
from noc.store.targets import (
    add_target,
    apply_inventory,
    find_target,
    get_target,
    list_resources,
    rotate_hmac_key,
    set_auto_actions,
    set_automation,
    set_profile,
    set_variant_override,
)
from noc.tools.sentinel_client import SentinelDirectory, build_sentinel_http
from noc.tools.spec import TargetRef
from noc.worker.all_in_one import run_all_in_one
from noc.worker.main import run_worker
from noc_shared.taxonomy import RootCauseCode

app = typer.Typer(help="Multi-Agent NOC command line", no_args_is_help=True)
targets_app = typer.Typer(help="Manage monitored targets", no_args_is_help=True)
incidents_app = typer.Typer(help="Inspect incidents", no_args_is_help=True)
db_app = typer.Typer(help="Database tasks", no_args_is_help=True)
audit_app = typer.Typer(help="Audit log", no_args_is_help=True)
scenario_app = typer.Typer(
    help="Inject and score deterministic failure scenarios", no_args_is_help=True
)
users_app = typer.Typer(help="Manage dashboard users", no_args_is_help=True)
eval_app = typer.Typer(help="Plan and summarize evaluation runs", no_args_is_help=True)
app.add_typer(targets_app, name="targets")
app.add_typer(incidents_app, name="incidents")
app.add_typer(db_app, name="db")
app.add_typer(audit_app, name="audit")
app.add_typer(scenario_app, name="scenario")
app.add_typer(users_app, name="users")
app.add_typer(eval_app, name="eval")


def with_sessions[ResultT](work: Callable[[SessionFactory], Awaitable[ResultT]]) -> ResultT:
    async def runner() -> ResultT:
        engine = create_engine(get_settings().database_url, pool_size=2)
        try:
            return await work(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(runner())


def with_admin_sessions[ResultT](work: Callable[[SessionFactory], Awaitable[ResultT]]) -> ResultT:
    try:
        return with_sessions(work)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000) -> None:
    configure_logging()
    uvicorn.run(create_app(get_settings()), host=host, port=port, proxy_headers=False)


@app.command()
def worker() -> None:
    configure_logging()
    asyncio.run(run_worker(get_settings()))


@app.command("all-in-one")
def all_in_one(host: str = "127.0.0.1", port: int = 8000) -> None:
    configure_logging()
    asyncio.run(run_all_in_one(get_settings(), host, port))


def alembic_config() -> Config:
    config = Config(str(PACKAGE_DIR / "db" / "alembic.ini"))
    config.set_main_option("script_location", str(PACKAGE_DIR / "db" / "migrations"))
    return config


@eval_app.command("plan")
def eval_plan(plan_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    plan = load_plan(plan_file)

    async def work(sessions: SessionFactory) -> tuple[int, dict[str, int]]:
        async with transaction(sessions) as session:
            created = await materialize(session, plan)
            return created, await status_counts(session, plan.name)

    created, counts = with_sessions(work)
    typer.echo(f"{plan.name}: {created} new runs scheduled")
    for status, count in sorted(counts.items()):
        typer.echo(f"  {status:<8} {count}")


@eval_app.command("run")
def eval_run(
    plan_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    target: Annotated[str, typer.Option(help="Lab target to inject on, e.g. demo-1")],
    limit: Annotated[int | None, typer.Option(help="Stop after this many finished runs")] = None,
    reset_seconds: Annotated[float, typer.Option(help="Pause between runs")] = 60.0,
    provider_wait_seconds: Annotated[
        float, typer.Option(help="Pause after a run lost to a model provider failure")
    ] = 900.0,
) -> None:
    settings = get_settings()
    if not settings.eval_mode:
        raise typer.BadParameter("set NOC_EVAL_MODE=true for the worker and this command")
    plan = load_plan(plan_file)
    scenarios = load_scenarios(settings.scenarios_dir)
    loop_settings = LoopSettings(
        target=target, reset_seconds=reset_seconds, provider_wait_seconds=provider_wait_seconds
    )

    async def work(sessions: SessionFactory) -> list[str]:
        async with transaction(sessions) as session:
            await materialize(session, plan)
        runner = build_scenario_runner(sessions, await target_sentinel_url(sessions, target))
        loop = EvalLoop(sessions, runner, scenarios, loop_settings, utc_now, asyncio.sleep)
        summary = await loop.run(plan.name, limit)
        lines = [
            *summary.messages,
            f"{plan.name}: {summary.done} done, {summary.invalid} invalid, "
            f"{summary.requeued} re-queued",
        ]
        if summary.stopped_reason is not None:
            lines.append(f"stopped: {summary.stopped_reason}")
        return lines

    try:
        lines = with_admin_sessions(work)
    except ChaosError as error:
        typer.echo(f"sentinel rejected chaos request: {error.code}", err=True)
        raise typer.Exit(1) from error
    for line in lines:
        typer.echo(line)


@eval_app.command("status")
def eval_status(plan_name: str) -> None:
    async def work(sessions: SessionFactory) -> dict[str, int]:
        async with sessions() as session:
            return await status_counts(session, plan_name)

    counts = with_sessions(work)
    if not counts:
        raise typer.BadParameter(f"no runs for plan {plan_name}")
    for status, count in sorted(counts.items()):
        typer.echo(f"{status:<8} {count}")


@eval_app.command("export")
def eval_export(
    plan_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    scenarios_dir: Path | None = None,
) -> None:
    plan = load_plan(plan_file)
    definitions = load_scenarios(scenarios_dir or get_settings().scenarios_dir)
    expected = {name: item.ground_truth.expected_outcome for name, item in definitions.items()}

    async def work(sessions: SessionFactory) -> str:
        async with sessions() as session:
            records = await load_records(session, plan.name, expected)
        return to_csv(summarize_all(records))

    typer.echo(with_sessions(work), nl=False)


@app.command()
def doctor() -> None:
    settings = get_settings()
    expected_head = ScriptDirectory.from_config(alembic_config()).get_current_head() or ""

    async def work(sessions: SessionFactory) -> list[CheckResult]:
        async with sessions() as session:
            targets = list(await session.scalars(select(Target).order_by(Target.name)))
            running_eval = await session.scalar(
                select(EvalRun.id).where(EvalRun.status == "running").limit(1)
            )
        return [
            await check_database(sessions, expected_head),
            check_policy(settings.policy_file),
            await check_prometheus(settings.prometheus_url),
            check_llm(settings, dict(os.environ)),
            check_secrets_dir(settings.secrets_dir),
            check_external_heartbeat(settings),
            check_variant_overrides(targets, running_eval is not None),
            *await check_targets(settings, targets),
        ]

    results = with_sessions(work)
    for result in results:
        typer.echo(f"{result.status.upper():<5} {result.name:<28} {result.detail}")
    if any(result.status == "fail" for result in results):
        raise typer.Exit(code=1)


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


@db_app.command("downgrade")
def db_downgrade(revision: str) -> None:
    command.downgrade(alembic_config(), revision)


@db_app.command("revision")
def db_revision(message: str) -> None:
    command.revision(alembic_config(), message=message, autogenerate=True)


@targets_app.command("add")
def targets_add(
    name: str,
    address: str,
    sentinel_url: str,
    key_id: Annotated[str, typer.Option(help="HMAC key id shared with the sentinel")],
    env: Annotated[Environment, typer.Option()] = Environment.PROD,
    automation: Annotated[AutomationLevel | None, typer.Option()] = None,
) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            target = await add_target(session, name, address, sentinel_url, env, key_id, automation)
            await append_audit(session, "cli", "target_added", name, {"env": env.value})
            return f"{target.name}: env={target.environment} automation={target.automation_level}"

    typer.echo(with_sessions(work))


@targets_app.command("list")
def targets_list() -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            rows = await session.scalars(select(Target).order_by(Target.name))
            return [
                f"{t.name:<16} {t.environment:<5} {t.automation_level:<18} {t.sentinel_url}"
                for t in rows
            ]

    for line in with_sessions(work):
        typer.echo(line)


@targets_app.command("sync")
def targets_sync(name: str) -> None:
    settings = get_settings()

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            target = await find_target(session, name)
            if target is None:
                raise typer.BadParameter(f"unknown target {name}")
            reference = TargetRef(
                id=target.id,
                name=target.name,
                sentinel_url=target.sentinel_url,
                hmac_key_id=target.hmac_key_id,
                environment=target.environment,
                data_policy=target.llm_data_policy,
            )
            http = build_sentinel_http(
                settings.sentinel_ca_file,
                settings.sentinel_client_cert,
                settings.sentinel_client_key,
                settings.sentinel_timeout_seconds,
            )
            async with http:
                inventory = (
                    await SentinelDirectory(settings.sentinel_key_dir, http)
                    .client_for(reference)
                    .inventory()
                )
            count = await apply_inventory(session, target, inventory)
            return f"{name}: {count} managed resources, halted={inventory.halted}"

    typer.echo(with_sessions(work))


KEY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$"
GENERATED_KEY_BYTES = 32
KEY_FILE_MODE = 0o600


@targets_app.command("rotate-key")
def targets_rotate_key(
    name: str,
    new_key_id: Annotated[str, typer.Option(help="Id of the new HMAC key")],
    generate: Annotated[
        bool, typer.Option("--generate", help="Create the new key file in the key directory")
    ] = False,
    activate: Annotated[
        bool, typer.Option("--activate", help="Start signing with the new key after a live check")
    ] = False,
) -> None:
    if generate == activate:
        raise typer.BadParameter("use exactly one of --generate and --activate")
    if re.fullmatch(KEY_ID_PATTERN, new_key_id) is None:
        raise typer.BadParameter("key ids use letters, digits, dot, dash and underscore")
    settings = get_settings()
    key_file = settings.sentinel_key_dir / f"{new_key_id}.key"
    if generate:
        typer.echo(generate_key_file(key_file))
        return
    typer.echo(activate_key(settings, name, new_key_id))


def generate_key_file(key_file: Path) -> str:
    if key_file.exists():
        raise typer.BadParameter(f"{key_file} already exists; refusing to overwrite a key")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, KEY_FILE_MODE)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(secrets.token_hex(GENERATED_KEY_BYTES) + "\n")
    return (
        f"wrote {key_file} (owner only)\n"
        f"next: copy the file to the target, add it to key_files in the sentinel config next to "
        f"the old key, restart the sentinel, then run this command again with --activate"
    )


def activate_key(settings: Settings, name: str, new_key_id: str) -> str:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            target = await find_target(session, name)
            if target is None:
                raise typer.BadParameter(f"unknown target {name}")
            reference = TargetRef(
                id=target.id,
                name=target.name,
                sentinel_url=target.sentinel_url,
                hmac_key_id=new_key_id,
                environment=target.environment,
                data_policy=target.llm_data_policy,
            )
            http = build_sentinel_http(
                settings.sentinel_ca_file,
                settings.sentinel_client_cert,
                settings.sentinel_client_key,
                settings.sentinel_timeout_seconds,
            )
            try:
                async with http:
                    await (
                        SentinelDirectory(settings.sentinel_key_dir, http)
                        .client_for(reference)
                        .inventory()
                    )
            except Exception as error:
                raise typer.BadParameter(
                    f"the sentinel did not accept key {new_key_id}: {type(error).__name__}: {error}"
                ) from error
            try:
                previous = await rotate_hmac_key(session, name, new_key_id, "cli")
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
            return (
                f"{name}: now signing with {new_key_id} (was {previous}). Remove {previous} "
                f"from the sentinel's key_files and delete its file once nothing uses it."
            )

    return with_sessions(work)


@targets_app.command("render-sd")
def targets_render_sd(directory: Path) -> None:
    async def work(sessions: SessionFactory) -> list[Path]:
        async with sessions() as session:
            return render_file_sd(list(await session.scalars(select(Target))), directory)

    for path in with_sessions(work):
        typer.echo(f"wrote {path}")


@targets_app.command("show")
def targets_show(name: str) -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            target = await get_target(session, name)
            resources = await list_resources(session, target)
            lines = [
                f"name           {target.name}",
                f"address        {target.address}",
                f"sentinel       {target.sentinel_url}",
                f"environment    {target.environment}",
                f"automation     {target.automation_level}",
                f"data policy    {target.llm_data_policy}",
                f"hmac key       {target.hmac_key_id}",
                f"auto actions   {', '.join(target.auto_actions) or '-'}",
                f"variant        {target.variant_override or '-'}",
                f"halted         {target.halted}",
                f"last inventory {target.last_inventory_at or '-'}",
                "",
                f"{'resource':<32} {'kind':<12} {'profile':<8} allowed actions",
            ]
            lines += [
                f"{r.resource_id:<32} {r.kind:<12} {'yes' if r.profile else 'no':<8} "
                f"{', '.join(r.allowed_actions) or '-'}"
                for r in resources
            ]
            return lines

    for line in with_admin_sessions(work):
        typer.echo(line)


@targets_app.command("set-variant")
def targets_set_variant(
    name: str,
    variant: Annotated[
        str | None, typer.Argument(help="single, multi, multi-strong or runbook")
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Remove the override")] = False,
) -> None:
    if clear == (variant is not None):
        raise typer.BadParameter("give a variant or --clear, not both and not neither")
    chosen = parse_variant(variant)
    if variant is not None and chosen is None:
        raise typer.BadParameter(f"unknown variant {variant}; use {', '.join(VARIANTS)}")
    if chosen is not None and not get_settings().eval_mode:
        raise typer.BadParameter("set NOC_EVAL_MODE=true before overriding the variant")

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                target = await set_variant_override(session, name, chosen, "cli")
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
            return f"{target.name}: variant override={target.variant_override or '-'}"

    typer.echo(with_admin_sessions(work))


@targets_app.command("set-automation")
def targets_set_automation(name: str, level: AutomationLevel) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            target = await set_automation(session, name, level)
            await append_audit(
                session, "cli", "target_automation_set", name, {"level": level.value}
            )
            return f"{target.name}: automation={target.automation_level}"

    typer.echo(with_admin_sessions(work))


@targets_app.command("set-auto-actions")
def targets_set_auto_actions(
    name: str, actions: Annotated[list[str], typer.Argument(help="Policy action names")]
) -> None:
    known_actions = frozenset(load_policy(get_settings().policy_file).actions)

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            target = await set_auto_actions(session, name, actions, known_actions)
            await append_audit(
                session, "cli", "target_auto_actions_set", name, {"actions": list(actions)}
            )
            return f"{target.name}: auto actions={', '.join(target.auto_actions) or '-'}"

    typer.echo(with_admin_sessions(work))


@targets_app.command("set-profile")
def targets_set_profile(name: str, resource_id: str, json_file: Path) -> None:
    profile_json = json_file.read_text()

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            row = await set_profile(session, name, resource_id, profile_json)
            await append_audit(
                session,
                "cli",
                "target_profile_set",
                name,
                {"resource_id": resource_id, "profile": row.profile or {}},
            )
            return f"{name} {resource_id}: profile stored"

    typer.echo(with_admin_sessions(work))


@incidents_app.command("list")
def incidents_list(limit: int = 20) -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            rows = await session.scalars(
                select(Incident).order_by(Incident.opened_at.desc()).limit(limit)
            )
            return [
                f"{i.id}  {i.status:<14} {i.severity:<8} {i.root_cause_code or '-':<24} {i.title}"
                for i in rows
            ]

    for line in with_sessions(work):
        typer.echo(line)


@incidents_app.command("report")
def incidents_report(incident_id: uuid.UUID) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with sessions() as session:
            markdown = await session.scalar(
                select(Report.markdown).where(Report.incident_id == incident_id)
            )
            return markdown or "No report yet."

    typer.echo(with_sessions(work))


@incidents_app.command("close")
def incidents_close(
    incident_id: uuid.UUID,
    note: Annotated[str, typer.Option(help="Human resolution note, 1-2000 characters")],
    root_cause: Annotated[
        RootCauseCode | None, typer.Option(help="Corrected root cause code")
    ] = None,
) -> None:
    async def work(sessions: SessionFactory) -> str:
        resolution = IncidentResolution(resolution_note=note, corrected_root_cause_code=root_cause)
        async with transaction(sessions) as session:
            try:
                incident = await close_incident(session, incident_id, resolution, "cli")
            except (LookupError, InvalidTransition) as error:
                raise typer.BadParameter(str(error)) from error
            return f"{incident.id}: status={incident.status} root_cause={root_cause or '-'}"

    typer.echo(with_admin_sessions(work))


def decide_from_cli(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    decision: ApprovalDecision,
    action_hash: str,
    decided_by: str,
    comment: str | None,
) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                recorded = await record_approval(
                    session, incident_id, action_id, decision, decided_by, action_hash, comment
                )
            except (LookupError, ApprovalConflict) as error:
                raise typer.BadParameter(str(error)) from error
            return f"{decision}: approval={recorded.approval_id} status={recorded.incident_status}"

    typer.echo(with_sessions(work))


@incidents_app.command("approve")
def incidents_approve(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    action_hash: Annotated[str, typer.Option("--hash", help="action_hash shown with the action")],
    by: Annotated[str, typer.Option(help="Who approves, 1-64 characters")],
    comment: Annotated[str | None, typer.Option(help="Optional note")] = None,
) -> None:
    decide_from_cli(incident_id, action_id, "approved", action_hash, by, comment)


@incidents_app.command("reject")
def incidents_reject(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    action_hash: Annotated[str, typer.Option("--hash", help="action_hash shown with the action")],
    by: Annotated[str, typer.Option(help="Who rejects, 1-64 characters")],
    comment: Annotated[str | None, typer.Option(help="Optional note")] = None,
) -> None:
    decide_from_cli(incident_id, action_id, "rejected", action_hash, by, comment)


@incidents_app.command("actions")
def incidents_actions(incident_id: uuid.UUID) -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            rows = await session.scalars(
                select(ActionRow)
                .where(ActionRow.incident_id == incident_id)
                .order_by(ActionRow.rung, ActionRow.action_type)
            )
            return [
                f"{a.id}  {a.action_type:<16} {a.resource_id:<20} {a.status:<16} "
                f"{a.permission_class:<18} hash={a.action_hash}"
                for a in rows
            ]

    for line in with_sessions(work):
        typer.echo(line)


@audit_app.command("verify")
def audit_verify(
    anchors: Annotated[
        Path | None,
        typer.Option(help="Directory of anchor files to check the chain against"),
    ] = None,
) -> None:
    key_file = get_settings().audit_anchor_key_file
    loaded = [] if anchors is None else load_anchors(anchors)

    async def work(sessions: SessionFactory) -> tuple[int | None, list[str]]:
        async with sessions() as session:
            broken = await verify_chain(session)
            if anchors is None:
                return broken, []
            checks = await check_anchors(session, read_key(key_file), loaded)
        return broken, [f"{check.name}: {check.problem}" for check in checks if check.problem]

    try:
        broken, problems = with_sessions(work)
    except AnchorError as error:
        raise typer.BadParameter(str(error)) from error
    if broken is not None:
        typer.echo(f"audit chain broken at entry {broken}", err=True)
        raise typer.Exit(1)
    for problem in problems:
        typer.echo(f"anchor problem, {problem}", err=True)
    if problems:
        raise typer.Exit(1)
    typer.echo(
        "audit chain intact" if anchors is None else "audit chain intact and matches its anchors"
    )


@audit_app.command("anchor")
def audit_anchor(
    out: Annotated[
        Path | None, typer.Option(help="Directory to write the anchor file to; prints when unset")
    ] = None,
) -> None:
    key_file = get_settings().audit_anchor_key_file

    async def work(sessions: SessionFactory) -> tuple[str, str]:
        async with sessions() as session:
            anchor = await create_anchor(session, read_key(key_file), utc_now())
        return anchor_filename(anchor.body), anchor.model_dump_json(indent=2)

    try:
        name, text = with_sessions(work)
    except AnchorError as error:
        raise typer.BadParameter(str(error)) from error
    if out is None:
        typer.echo(text)
        return
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    target.write_text(text + "\n", encoding="utf-8")
    typer.echo(f"wrote {target}")


def read_password(password_stdin: bool) -> str:
    if password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password: str = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    return password


def describe_user(user: User) -> str:
    return f"{user.username}: role={user.role} disabled={user.disabled}"


def user_line(user: User) -> str:
    disabled = "yes" if user.disabled else "no"
    second_factor = "yes" if user.totp_enabled else "no"
    return (
        f"{user.username:<32} {user.role:<10} {disabled:<8} {second_factor:<4} "
        f"{user.last_login_at or '-'}"
    )


@users_app.command("create")
def users_create(
    username: str,
    role: Annotated[Role, typer.Option(help="viewer, operator or admin")],
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from one line of stdin")
    ] = False,
) -> None:
    password = read_password(password_stdin)

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            user = await create_user(session, username, password, role, "cli")
            return describe_user(user)

    typer.echo(with_admin_sessions(work))


@users_app.command("list")
def users_list() -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            return [user_line(user) for user in await list_users(session)]

    typer.echo(f"{'username':<32} {'role':<10} {'disabled':<8} {'2fa':<4} last_login")
    for line in with_sessions(work):
        typer.echo(line)


@users_app.command("disable")
def users_disable(username: str) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user = await set_disabled(session, username, True, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return describe_user(user)

    typer.echo(with_admin_sessions(work))


@users_app.command("enable")
def users_enable(username: str) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user = await set_disabled(session, username, False, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return describe_user(user)

    typer.echo(with_admin_sessions(work))


@users_app.command("set-role")
def users_set_role(username: str, role: Role) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user = await set_role(session, username, role, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return describe_user(user)

    typer.echo(with_admin_sessions(work))


@users_app.command("unlock")
def users_unlock(username: str) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                cleared = await unlock_user(session, username, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return f"{username}: cleared {cleared} failed login(s)"

    typer.echo(with_admin_sessions(work))


@users_app.command("delete")
def users_delete(
    username: str,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
) -> None:
    if not yes:
        typer.confirm(f"Remove {username} for good? Audit entries keep the name.", abort=True)

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                name = await delete_user(session, username, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return f"{name}: removed, sessions ended"

    typer.echo(with_admin_sessions(work))


@users_app.command("totp-enroll")
def users_totp_enroll(username: str) -> None:
    issuer = get_settings().totp_issuer

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user, secret = await enroll_totp(session, username, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return "\n".join(
                [
                    f"{user.username}: two-factor authentication is on, other sessions ended",
                    f"secret {secret}",
                    provisioning_uri(issuer, user.username, secret),
                ]
            )

    typer.echo(with_admin_sessions(work))


@users_app.command("totp-reset")
def users_totp_reset(username: str) -> None:
    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user = await require_user(session, username)
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            await clear_totp(session, user, "cli")
            return f"{user.username}: two-factor authentication is off, sessions ended"

    typer.echo(with_admin_sessions(work))


@users_app.command("reset-password")
def users_reset_password(
    username: str,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from one line of stdin")
    ] = False,
) -> None:
    password = read_password(password_stdin)

    async def work(sessions: SessionFactory) -> str:
        async with transaction(sessions) as session:
            try:
                user = await reset_password(session, username, password, "cli")
            except LookupError as error:
                raise typer.BadParameter(str(error)) from error
            return describe_user(user)

    typer.echo(with_admin_sessions(work))


def scenario_named(name: str) -> ScenarioDefinition:
    scenarios = load_scenarios(get_settings().scenarios_dir)
    if name not in scenarios:
        raise typer.BadParameter(f"unknown scenario {name}; known: {', '.join(sorted(scenarios))}")
    return scenarios[name]


async def target_sentinel_url(sessions: SessionFactory, name: str) -> str:
    async with sessions() as session:
        return (await get_target(session, name)).sentinel_url


def build_scenario_runner(sessions: SessionFactory, sentinel_url: str) -> ScenarioRunner:
    chaos = build_chaos_client(sentinel_url, get_settings())
    return ScenarioRunner(sessions, chaos, utc_now, asyncio.sleep)


def format_outcome(outcome: RunOutcome) -> list[str]:
    detection = "-" if outcome.detection_seconds is None else f"{outcome.detection_seconds:.0f}s"
    return [
        f"run {outcome.run_id}: {outcome.status}",
        f"detected after {detection}, final status {outcome.final_status or '-'}",
        f"root cause match: {outcome.root_cause_match}",
    ]


@scenario_app.command("list")
def scenario_list() -> None:
    for scenario in load_scenarios(get_settings().scenarios_dir).values():
        typer.echo(
            f"{scenario.name:<20} {scenario.injection.type:<14} "
            f"{injection_summary(scenario.injection):<20} {scenario.ground_truth.root_cause_code}"
        )


@scenario_app.command("run")
def scenario_run(
    name: str,
    target: Annotated[str, typer.Option(help="Target name, e.g. demo-1")],
    resource: Annotated[
        str | None, typer.Option(help="Service to inject on (service-down only)")
    ] = None,
) -> None:
    scenario = scenario_named(name)

    async def work(sessions: SessionFactory) -> list[str]:
        runner = build_scenario_runner(sessions, await target_sentinel_url(sessions, target))
        try:
            outcome = await runner.run(scenario, target, resource)
        except PreconditionFailed as error:
            raise typer.BadParameter(str(error)) from error
        return format_outcome(outcome)

    try:
        lines = with_admin_sessions(work)
    except ChaosError as error:
        typer.echo(f"sentinel rejected chaos request: {error.code}", err=True)
        raise typer.Exit(1) from error
    for line in lines:
        typer.echo(line)


@scenario_app.command("status")
def scenario_status(limit: int = 10) -> None:
    async def work(sessions: SessionFactory) -> list[str]:
        async with sessions() as session:
            rows = (
                await session.execute(
                    select(ScenarioRun, Target.name)
                    .join(Target, Target.id == ScenarioRun.target_id)
                    .order_by(ScenarioRun.injected_at.desc())
                    .limit(limit)
                )
            ).all()
        return [
            f"{run.injected_at:%Y-%m-%d %H:%M}  {run.scenario:<16} {target_name:<12} "
            f"{run.status:<10} final={run.final_status or '-':<14} "
            f"root_cause_match={run.root_cause_match}"
            for run, target_name in rows
        ]

    for line in with_sessions(work):
        typer.echo(line)


@scenario_app.command("stop")
def scenario_stop(
    target: Annotated[str, typer.Option(help="Target name, e.g. demo-1")],
    scenario: Annotated[
        str, typer.Option(help="Scenario whose injection kind should be restored")
    ] = "service-down",
    resource: Annotated[
        str | None, typer.Option(help="Service to restore (service_down only)")
    ] = None,
) -> None:
    definition = scenario_named(scenario)
    resource_id = run_resource(definition.injection, target, resource)

    async def work(sessions: SessionFactory) -> str:
        runner = build_scenario_runner(sessions, await target_sentinel_url(sessions, target))
        stopped = await runner.stop_injection(definition.injection.type, resource_id)
        return f"{resource_id}: restored" if stopped else f"{resource_id}: nothing active"

    try:
        message = with_admin_sessions(work)
    except ChaosError as error:
        typer.echo(f"sentinel rejected chaos request: {error.code}", err=True)
        raise typer.Exit(1) from error
    typer.echo(message)
