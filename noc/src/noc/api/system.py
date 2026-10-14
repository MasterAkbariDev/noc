import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.api.prometheus import PrometheusReader
from noc.api.schemas import ComponentHealth, ComponentStatus, StuckIncident, SystemHealth, Verdict
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Incident, IncidentEvent, Job, Target, WorkerHeartbeat
from noc.detection.alerts import PrometheusUnavailable
from noc.domain.incident_status import ACTIVE_STATUSES
from noc.llm.providers import ProvidersDocument, load_providers

router = APIRouter(
    prefix="/api/system", tags=["system"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
Connect = Callable[[str, int], Awaitable[object]]

LABELS = {
    "worker": "Worker",
    "alert_polling": "Alert polling",
    "prometheus": "Prometheus",
    "egress": "Egress proxy",
    "database": "Database",
    "version": "Version",
    "updater": "Updater",
}
STUCK_AFTER = timedelta(minutes=15)
WORKER_OK_BEATS = 3
WORKER_DEGRADED_AFTER = timedelta(minutes=5)
POLL_FRESH_FOR = timedelta(seconds=30)
EGRESS_TIMEOUT_SECONDS = 2.0
FAILED_UPDATE_RESULTS = frozenset({"failed", "rolled_back", "pull_failed"})
DATABASE_UNREADABLE = "The database did not answer, so this cannot be checked"


class UpdateStatus(BaseModel):
    ts: datetime
    result: str
    image: str
    message: str


@dataclass(frozen=True)
class DatabaseSnapshot:
    heartbeat: WorkerHeartbeat | None
    migration: str | None
    stuck: list[StuckIncident]


def component(
    key: str,
    status: ComponentStatus,
    summary: str,
    details: dict[str, str] | None = None,
    since: datetime | None = None,
) -> ComponentHealth:
    return ComponentHealth(
        key=key,
        label=LABELS[key],
        status=status,
        summary=summary,
        details=details or {},
        since=since,
    )


def describe_age(age: timedelta) -> str:
    seconds = max(int(age.total_seconds()), 0)
    if seconds < 120:
        return f"{seconds} s ago"
    if seconds < 7200:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago"


def verdict(components: list[ComponentHealth]) -> Verdict:
    statuses = {item.key: item.status for item in components}
    if statuses["worker"] == "down" or statuses["database"] == "down":
        return "down"
    if any(item.status in {"degraded", "down"} for item in components):
        return "degraded"
    return "ok"


def worker_component(
    snapshot: DatabaseSnapshot | None, interval_seconds: float, now: datetime
) -> ComponentHealth:
    if snapshot is None:
        return component("worker", "unknown", DATABASE_UNREADABLE)
    beat = snapshot.heartbeat
    if beat is None:
        return component("worker", "down", "The worker has never reported")
    age = now - beat.last_beat_at
    status: ComponentStatus
    if age <= timedelta(seconds=interval_seconds * WORKER_OK_BEATS):
        status = "ok"
    elif age <= WORKER_DEGRADED_AFTER:
        status = "degraded"
    else:
        status = "down"
    return component(
        "worker",
        status,
        f"Last heartbeat {describe_age(age)}",
        {"version": beat.version},
        beat.started_at,
    )


def alert_polling_component(snapshot: DatabaseSnapshot | None, now: datetime) -> ComponentHealth:
    if snapshot is None:
        return component("alert_polling", "unknown", DATABASE_UNREADABLE)
    beat = snapshot.heartbeat
    if beat is None:
        return component(
            "alert_polling", "unknown", "No worker has reported, so polling is unknown"
        )
    details = {"last_error": beat.last_poll_error} if beat.last_poll_error else {}
    if beat.last_poll_ok_at is None:
        return component(
            "alert_polling",
            "degraded",
            with_last_error("No alert poll has succeeded yet", beat.last_poll_error),
            details,
        )
    age = now - beat.last_poll_ok_at
    if age <= POLL_FRESH_FOR:
        return component(
            "alert_polling",
            "ok",
            f"Last alert poll succeeded {describe_age(age)}",
            details,
            beat.last_poll_ok_at,
        )
    return component(
        "alert_polling",
        "degraded",
        with_last_error(f"Last alert poll succeeded {describe_age(age)}", beat.last_poll_error),
        details,
        beat.last_poll_ok_at,
    )


def with_last_error(summary: str, error: str | None) -> str:
    return f"{summary}; last error: {error}" if error else summary


async def prometheus_component(reader: PrometheusReader) -> ComponentHealth:
    try:
        targets = await reader.targets()
    except PrometheusUnavailable:
        return component("prometheus", "down", "Prometheus cannot be reached")
    if not targets:
        return component("prometheus", "unknown", "Prometheus lists no scrape targets")
    up = sum(1 for target in targets if target.health == "up")
    details = {"up": f"{up}/{len(targets)}"}
    if up == len(targets):
        return component("prometheus", "ok", f"All {len(targets)} scrape targets are up", details)
    return component(
        "prometheus",
        "degraded",
        f"{len(targets) - up} of {len(targets)} scrape targets are down",
        details,
    )


def proxy_endpoints(providers: ProvidersDocument) -> dict[str, tuple[str, int]]:
    endpoints: dict[str, tuple[str, int]] = {}
    for name, provider in providers.providers.items():
        proxy = provider.proxy_url()
        if proxy is None:
            continue
        parts = urlsplit(proxy)
        if parts.hostname is None:
            continue
        default_port = 443 if parts.scheme == "https" else 80
        endpoints[name] = (parts.hostname, parts.port or default_port)
    return endpoints


async def open_tcp(host: str, port: int) -> None:
    _, writer = await asyncio.open_connection(host, port)
    writer.close()
    await writer.wait_closed()


async def probe_proxy(connect: Connect, name: str, host: str, port: int) -> tuple[str, str]:
    try:
        await asyncio.wait_for(connect(host, port), EGRESS_TIMEOUT_SECONDS)
    except (OSError, TimeoutError):
        return name, "unreachable"
    return name, "reachable"


async def egress_component(
    endpoints: dict[str, tuple[str, int]], connect: Connect
) -> ComponentHealth:
    if not endpoints:
        return component("egress", "unknown", "No egress proxy configured")
    results = await asyncio.gather(
        *(probe_proxy(connect, name, host, port) for name, (host, port) in endpoints.items())
    )
    details = dict(results)
    unreachable = [name for name, state in results if state != "reachable"]
    if not unreachable:
        return component(
            "egress", "ok", f"All {len(endpoints)} egress proxies accept connections", details
        )
    return component(
        "egress",
        "down",
        f"{len(unreachable)} of {len(endpoints)} egress proxies are unreachable",
        details,
    )


def database_component(snapshot: DatabaseSnapshot | None) -> ComponentHealth:
    if snapshot is None:
        return component("database", "down", "The database did not answer")
    return component(
        "database",
        "ok",
        "The database answers queries",
        {"migration": snapshot.migration or "unknown"},
    )


def version_component(settings: Settings) -> ComponentHealth:
    return component(
        "version",
        "ok",
        f"NOC {settings.version} ({settings.git_sha[:12]})",
        {"version": settings.version, "git_sha": settings.git_sha},
    )


def updater_component(path: Path | None) -> ComponentHealth:
    if path is None:
        return component("updater", "unknown", "No update status file is configured")
    try:
        status = UpdateStatus.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return component("updater", "unknown", "The updater has not written a status yet")
    except (OSError, ValueError):
        return component("updater", "unknown", "The update status file cannot be read")
    details = {"result": status.result, "image": status.image, "message": status.message}
    status_name: ComponentStatus = "degraded" if status.result in FAILED_UPDATE_RESULTS else "ok"
    return component("updater", status_name, status.message, details, status.ts)


async def migration_revision(session: AsyncSession) -> str | None:
    exists: bool = await session.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
    if not exists:
        return None
    revision: str | None = await session.scalar(text("SELECT version_num FROM alembic_version"))
    return revision


async def newest_jobs(session: AsyncSession, incident_ids: list[str]) -> dict[str, Job]:
    if not incident_ids:
        return {}
    incident_key = Job.payload["incident_id"].astext
    rows = await session.scalars(
        select(Job)
        .where(incident_key.in_(incident_ids))
        .ext(distinct_on(incident_key))
        .order_by(incident_key, Job.id.desc())
    )
    return {str(job.payload["incident_id"]): job for job in rows}


async def stuck_incidents(session: AsyncSession, now: datetime) -> list[StuckIncident]:
    active = [status.value for status in ACTIVE_STATUSES]
    last_event = (
        select(IncidentEvent.incident_id, func.max(IncidentEvent.ts).label("last_ts"))
        .join(Incident, Incident.id == IncidentEvent.incident_id)
        .where(Incident.status.in_(active))
        .group_by(IncidentEvent.incident_id)
        .subquery()
    )
    since = func.coalesce(last_event.c.last_ts, Incident.opened_at)
    rows = await session.execute(
        select(Incident, Target.name, since.label("since"))
        .join(Target, Target.id == Incident.target_id)
        .outerjoin(last_event, last_event.c.incident_id == Incident.id)
        .where(Incident.status.in_(active), since < now - STUCK_AFTER)
        .order_by(since)
    )
    found = rows.all()
    jobs = await newest_jobs(session, [str(incident.id) for incident, _, _ in found])
    return [
        stuck_view(incident, target_name, started, jobs.get(str(incident.id)))
        for incident, target_name, started in found
    ]


def stuck_view(
    incident: Incident, target_name: str, started: datetime, job: Job | None
) -> StuckIncident:
    return StuckIncident(
        id=incident.id,
        title=incident.title,
        target=target_name,
        status=incident.status,
        since=started,
        job_status=job.status if job else None,
        job_attempts=job.attempts if job else None,
        job_last_error=job.last_error if job else None,
    )


async def read_snapshot(session: AsyncSession, now: datetime) -> DatabaseSnapshot | None:
    try:
        heartbeat = await session.scalar(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_beat_at.desc()).limit(1)
        )
        migration = await migration_revision(session)
        stuck = await stuck_incidents(session, now)
    except SQLAlchemyError:
        await session.rollback()
        return None
    return DatabaseSnapshot(heartbeat=heartbeat, migration=migration, stuck=stuck)


@router.get("/health")
async def system_health(request: Request, session: Session) -> SystemHealth:
    settings: Settings = request.app.state.settings
    prometheus: PrometheusReader = request.app.state.prometheus
    now = utc_now()
    snapshot = await read_snapshot(session, now)
    providers = load_providers(settings.llm_providers_file)
    components = [
        worker_component(snapshot, settings.worker_heartbeat_seconds, now),
        alert_polling_component(snapshot, now),
        await prometheus_component(prometheus),
        await egress_component(proxy_endpoints(providers), open_tcp),
        database_component(snapshot),
        version_component(settings),
        updater_component(settings.update_status_file),
    ]
    return SystemHealth(
        verdict=verdict(components),
        checked_at=now,
        components=components,
        stuck_incidents=snapshot.stuck if snapshot else [],
    )
