import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from noc.api.app import create_app
from noc.audit.chain import append_audit, verify_chain
from noc.config import PACKAGE_DIR, get_settings
from noc.db.base import utc_now
from noc.db.models import Incident, Report, ScenarioRun, Target
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.file_sd import render_file_sd
from noc.domain.incident_status import InvalidTransition
from noc.logging import configure_logging
from noc.policy.loader import load_policy
from noc.policy.models import AutomationLevel, Environment
from noc.scenarios.chaos_client import ChaosError, build_chaos_client
from noc.scenarios.definitions import ScenarioDefinition, load_scenarios
from noc.scenarios.runner import PreconditionFailed, RunOutcome, ScenarioRunner
from noc.store.incidents import IncidentResolution, close_incident
from noc.store.targets import (
    add_target,
    apply_inventory,
    find_target,
    get_target,
    list_resources,
    set_auto_actions,
    set_automation,
    set_profile,
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
app.add_typer(targets_app, name="targets")
app.add_typer(incidents_app, name="incidents")
app.add_typer(db_app, name="db")
app.add_typer(audit_app, name="audit")
app.add_typer(scenario_app, name="scenario")


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
    uvicorn.run(create_app(get_settings()), host=host, port=port)


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


@audit_app.command("verify")
def audit_verify() -> None:
    async def work(sessions: SessionFactory) -> int | None:
        async with sessions() as session:
            return await verify_chain(session)

    broken = with_sessions(work)
    if broken is None:
        typer.echo("audit chain intact")
        return
    typer.echo(f"audit chain broken at entry {broken}", err=True)
    raise typer.Exit(1)


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
            f"{scenario.injection.resource_id:<20} {scenario.ground_truth.root_cause_code}"
        )


@scenario_app.command("run")
def scenario_run(
    name: str,
    target: Annotated[str, typer.Option(help="Target name, e.g. demo-1")],
    resource: Annotated[
        str | None, typer.Option(help="Resource to inject on (default: the scenario's own)")
    ] = None,
) -> None:
    scenario = scenario_named(name)
    resource_id = resource or scenario.injection.resource_id

    async def work(sessions: SessionFactory) -> list[str]:
        runner = build_scenario_runner(sessions, await target_sentinel_url(sessions, target))
        try:
            outcome = await runner.run(scenario, target, resource_id)
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
    resource: Annotated[str, typer.Option(help="Resource whose injection should be restored")],
) -> None:
    async def work(sessions: SessionFactory) -> str:
        runner = build_scenario_runner(sessions, await target_sentinel_url(sessions, target))
        stopped = await runner.stop_injection(resource)
        return f"{resource}: restored" if stopped else f"{resource}: nothing active"

    try:
        message = with_admin_sessions(work)
    except ChaosError as error:
        typer.echo(f"sentinel rejected chaos request: {error.code}", err=True)
        raise typer.Exit(1) from error
    typer.echo(message)
