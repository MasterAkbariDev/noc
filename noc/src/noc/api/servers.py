import asyncio
import math
import uuid
from collections import defaultdict
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, require_role
from noc.api.incidents import summarize
from noc.api.prometheus import PrometheusReader, Sample, ScrapeTarget
from noc.api.schemas import (
    IncidentSummary,
    ServerDetail,
    ServerMetrics,
    ServerStatus,
    ServerSummary,
    ServiceState,
    TargetResourceView,
)
from noc.audit.chain import append_audit
from noc.auth.roles import Role
from noc.db.models import Incident, ManagedResourceRow, Target
from noc.detection.alerts import PrometheusUnavailable
from noc.domain.incident_status import OPEN_STATUSES
from noc.domain.severity import Severity
from noc.reporting import plain_language as words
from noc_shared.resources import ResourceKind

router = APIRouter(
    prefix="/api/servers", tags=["servers"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]

TARGET_LABEL = "target"
RESOURCE_LABEL = "resource"
MOUNT_LABEL = "mountpoint"
CPU_QUERY = f"max by ({TARGET_LABEL}) (host:cpu_utilization:ratio_rate2m)"
MEMORY_QUERY = f"max by ({TARGET_LABEL}) (1 - host:memory_available:ratio)"
DISK_QUERY = f"max by ({TARGET_LABEL}, {MOUNT_LABEL}) (1 - host:fs_avail:ratio)"
SERVICE_QUERY = f"max by ({TARGET_LABEL}, {RESOURCE_LABEL}) (noc_service_up)"
SERVICE_KINDS = frozenset({ResourceKind.SYSTEMD_UNIT.value, ResourceKind.CONTAINER.value})
SERVICE_UP = 1.0
PERCENT = 100
ATTENTION_PERCENT = 90
RECENT_INCIDENTS = 10
NOT_REACHABLE = "Not reachable"
STATUS_UNKNOWN = "Status unknown"
HALTED_TEXT = "Halted — automation stopped"
HEALTHY_TEXT = "Healthy"


@dataclass(frozen=True)
class FleetReadings:
    scrape_targets: list[ScrapeTarget] | None
    cpu: list[Sample] | None
    memory: list[Sample] | None
    disk: list[Sample] | None
    services: list[Sample] | None


def samples_by_target(samples: list[Sample] | None) -> dict[str, list[Sample]]:
    grouped: defaultdict[str, list[Sample]] = defaultdict(list)
    for sample in samples or []:
        if math.isfinite(sample.value):
            grouped[sample.labels.get(TARGET_LABEL, "")].append(sample)
    return grouped


def highest_sample(samples: list[Sample]) -> Sample | None:
    return max(samples, key=lambda sample: sample.value, default=None)


def percent(sample: Sample | None) -> float | None:
    return None if sample is None else round(sample.value * PERCENT, 1)


def metrics_for(name: str, readings: FleetReadings) -> ServerMetrics | None:
    cpu = highest_sample(samples_by_target(readings.cpu).get(name, []))
    memory = highest_sample(samples_by_target(readings.memory).get(name, []))
    disk = highest_sample(samples_by_target(readings.disk).get(name, []))
    if cpu is None and memory is None and disk is None:
        return None
    return ServerMetrics(
        cpu_percent=percent(cpu),
        memory_percent=percent(memory),
        disk_percent=percent(disk),
        disk_mount=disk.labels.get(MOUNT_LABEL) if disk is not None else None,
    )


def scrape_status(
    scrape_targets: list[ScrapeTarget] | None, name: str
) -> tuple[ServerStatus, datetime | None]:
    own = [item for item in scrape_targets or [] if item.labels.get(TARGET_LABEL) == name]
    if not own:
        return "unknown", None
    last_scrape = max(
        (item.last_scrape for item in own if item.last_scrape is not None), default=None
    )
    if any(item.health == "down" for item in own):
        return "down", last_scrape
    if all(item.health == "up" for item in own):
        return "up", last_scrape
    return "unknown", last_scrape


def worst_severity(incidents: list[Incident]) -> Severity | None:
    if not incidents:
        return None
    return Severity.highest(*(Severity.parse(item.severity) for item in incidents))


def usage_concerns(metrics: ServerMetrics | None) -> list[str]:
    if metrics is None:
        return []
    checks = (
        (metrics.disk_percent, "Disk {}% full"),
        (metrics.memory_percent, "Memory {}% used"),
        (metrics.cpu_percent, "CPU {}% busy"),
    )
    return [
        template.format(round(value))
        for value, template in checks
        if value is not None and value >= ATTENTION_PERCENT
    ]


def incident_phrase(count: int) -> str:
    return "1 open incident" if count == 1 else f"{count} open incidents"


def headline(
    status: ServerStatus, halted: bool, metrics: ServerMetrics | None, open_count: int
) -> str:
    parts: list[str] = []
    if status == "down":
        parts.append(NOT_REACHABLE)
    elif status == "unknown":
        parts.append(STATUS_UNKNOWN)
    parts.extend(usage_concerns(metrics))
    if halted:
        parts.append(HALTED_TEXT)
    if open_count:
        parts.append(incident_phrase(open_count))
    return " · ".join(parts) or HEALTHY_TEXT


def server_summary(
    target: Target, readings: FleetReadings, incidents: list[Incident]
) -> ServerSummary:
    status, last_scrape = scrape_status(readings.scrape_targets, target.name)
    metrics = metrics_for(target.name, readings)
    worst = worst_severity(incidents)
    return ServerSummary(
        id=target.id,
        name=target.name,
        label=target.label,
        tag=target.tag,
        environment=target.environment,
        automation_level=target.automation_level,
        automation_label=words.text_for(words.AUTOMATION_LABELS, target.automation_level),
        halted=target.halted,
        status=status,
        last_scrape_at=last_scrape,
        metrics=metrics,
        open_incidents=len(incidents),
        worst_severity=worst.value if worst is not None else None,
        headline=headline(status, target.halted, metrics, len(incidents)),
    )


def service_up(value: float | None) -> bool | None:
    return None if value is None else value == SERVICE_UP


def service_states(
    resources: list[ManagedResourceRow], services: list[Sample] | None, name: str
) -> list[ServiceState]:
    up_by_resource = {
        sample.labels.get(RESOURCE_LABEL, ""): sample.value
        for sample in samples_by_target(services).get(name, [])
    }
    return [
        ServiceState(
            resource_id=row.resource_id,
            name=row.name,
            up=service_up(up_by_resource.get(row.resource_id)),
        )
        for row in resources
        if row.kind in SERVICE_KINDS
    ]


async def reading_or_none[T](call: Awaitable[T]) -> T | None:
    try:
        return await call
    except PrometheusUnavailable:
        return None


async def read_fleet(reader: PrometheusReader) -> FleetReadings:
    scrape_targets, cpu, memory, disk, services = await asyncio.gather(
        reading_or_none(reader.targets()),
        reading_or_none(reader.vector(CPU_QUERY)),
        reading_or_none(reader.vector(MEMORY_QUERY)),
        reading_or_none(reader.vector(DISK_QUERY)),
        reading_or_none(reader.vector(SERVICE_QUERY)),
    )
    return FleetReadings(
        scrape_targets=scrape_targets,
        cpu=cpu,
        memory=memory,
        disk=disk,
        services=services,
    )


async def open_incidents_by_target(session: AsyncSession) -> dict[uuid.UUID, list[Incident]]:
    open_statuses = [status.value for status in OPEN_STATUSES]
    grouped: defaultdict[uuid.UUID, list[Incident]] = defaultdict(list)
    for incident in await session.scalars(
        select(Incident).where(Incident.status.in_(open_statuses))
    ):
        grouped[incident.target_id].append(incident)
    return grouped


async def load_server_summaries(
    session: AsyncSession, reader: PrometheusReader
) -> list[ServerSummary]:
    targets = list(await session.scalars(select(Target).order_by(Target.name)))
    readings = await read_fleet(reader)
    open_incidents = await open_incidents_by_target(session)
    return [
        server_summary(target, readings, open_incidents.get(target.id, [])) for target in targets
    ]


@router.get("")
async def list_servers(request: Request, session: Session) -> list[ServerSummary]:
    reader: PrometheusReader = request.app.state.prometheus
    return await load_server_summaries(session, reader)


@router.get("/{server_id}")
async def get_server(server_id: uuid.UUID, request: Request, session: Session) -> ServerDetail:
    target = await session.get(Target, server_id)
    if target is None:
        raise HTTPException(404, "server not found")
    reader: PrometheusReader = request.app.state.prometheus
    readings = await read_fleet(reader)
    open_incidents = await open_incidents_by_target(session)
    summary = server_summary(target, readings, open_incidents.get(target.id, []))
    resources = list(
        await session.scalars(
            select(ManagedResourceRow)
            .where(ManagedResourceRow.target_id == target.id)
            .order_by(ManagedResourceRow.resource_id)
        )
    )
    recent: list[IncidentSummary] = [
        summarize(incident, target.name)
        for incident in await session.scalars(
            select(Incident)
            .where(Incident.target_id == target.id)
            .order_by(Incident.opened_at.desc())
            .limit(RECENT_INCIDENTS)
        )
    ]
    return ServerDetail(
        **summary.model_dump(),
        last_inventory_at=target.last_inventory_at,
        resources=[TargetResourceView.model_validate(row) for row in resources],
        services=service_states(resources, readings.services, target.name),
        recent_incidents=recent,
    )


AUTOMATION_LEVELS = ("observe_only", "approval_required", "auto_safe")


class SetAutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field(max_length=32)


async def apply_automation(
    session: AsyncSession, name: str, level: str, actor: str
) -> dict[str, str]:
    if level not in AUTOMATION_LEVELS:
        raise HTTPException(422, f"the mode must be one of {', '.join(AUTOMATION_LEVELS)}")
    target = await session.scalar(select(Target).where(Target.name == name))
    if target is None:
        raise HTTPException(404, "server not found")
    previous = target.automation_level
    target.automation_level = level
    await append_audit(
        session,
        actor,
        "server_automation_set",
        f"target:{name}",
        {"from": previous, "to": level},
    )
    return {"name": name, "automation_level": level}


@router.put("/{name}/automation")
async def set_automation(
    name: str,
    body: SetAutomationRequest,
    admin: Annotated[Principal, Depends(require_role(Role.ADMIN))],
    session: Session,
) -> dict[str, str]:
    result = await apply_automation(session, name, body.level, admin.username)
    await session.commit()
    return result


TAGS = ("panel host",)


class SetTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str | None = Field(default=None, max_length=32)


@router.put("/{name}/tag")
async def set_tag(
    name: str,
    body: SetTagRequest,
    admin: Annotated[Principal, Depends(require_role(Role.ADMIN))],
    session: Session,
) -> dict[str, str | None]:
    if body.tag is not None and body.tag not in TAGS:
        raise HTTPException(422, f"the tag must be one of: {', '.join(TAGS)}")
    target = await session.scalar(select(Target).where(Target.name == name))
    if target is None:
        raise HTTPException(404, "server not found")
    previous = target.tag
    target.tag = body.tag
    await append_audit(
        session,
        admin.username,
        "server_tag_set",
        f"target:{name}",
        {"from": previous, "to": body.tag},
    )
    await session.commit()
    return {"name": name, "tag": target.tag}


class SetLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=64)


@router.put("/{name}/label")
async def set_label(
    name: str,
    body: SetLabelRequest,
    admin: Annotated[Principal, Depends(require_role(Role.ADMIN))],
    session: Session,
) -> dict[str, str | None]:
    target = await session.scalar(select(Target).where(Target.name == name))
    if target is None:
        raise HTTPException(404, "server not found")
    cleaned = body.label.strip() if body.label else None
    target.label = cleaned or None
    await append_audit(
        session, admin.username, "server_label_set", f"target:{name}", {"label": target.label}
    )
    await session.commit()
    return {"name": name, "label": target.label}
