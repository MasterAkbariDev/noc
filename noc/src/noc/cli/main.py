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
from noc.db.models import Incident, Report, Target
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.file_sd import render_file_sd
from noc.logging import configure_logging
from noc.policy.models import AutomationLevel, Environment
from noc.store.targets import add_target, apply_inventory, find_target
from noc.tools.sentinel_client import SentinelDirectory, build_sentinel_http
from noc.tools.spec import TargetRef
from noc.worker.main import run_worker

app = typer.Typer(help="Multi-Agent NOC command line", no_args_is_help=True)
targets_app = typer.Typer(help="Manage monitored targets", no_args_is_help=True)
incidents_app = typer.Typer(help="Inspect incidents", no_args_is_help=True)
db_app = typer.Typer(help="Database tasks", no_args_is_help=True)
audit_app = typer.Typer(help="Audit log", no_args_is_help=True)
app.add_typer(targets_app, name="targets")
app.add_typer(incidents_app, name="incidents")
app.add_typer(db_app, name="db")
app.add_typer(audit_app, name="audit")


def with_sessions[ResultT](work: Callable[[SessionFactory], Awaitable[ResultT]]) -> ResultT:
    async def runner() -> ResultT:
        engine = create_engine(get_settings().database_url, pool_size=2)
        try:
            return await work(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(runner())


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000) -> None:
    configure_logging()
    uvicorn.run(create_app(get_settings()), host=host, port=port)


@app.command()
def worker() -> None:
    configure_logging()
    asyncio.run(run_worker(get_settings()))


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
