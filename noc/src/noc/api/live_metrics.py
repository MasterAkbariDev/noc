import asyncio
import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.api.prometheus import Point, PrometheusReader, Sample, Series
from noc.api.schemas import FleetLive, FleetServerLive, LiveRange, ServerLive, ServiceLive
from noc.auth.roles import Role
from noc.db.models import Target
from noc.detection.alerts import PrometheusUnavailable

router = APIRouter(
    prefix="/api/live", tags=["live"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]

TARGET_LABEL = "target"
RESOURCE_LABEL = "resource"


@dataclass(frozen=True)
class Window:
    seconds: int
    step: int


WINDOWS: dict[str, Window] = {
    "15m": Window(seconds=15 * 60, step=15),
    "1h": Window(seconds=60 * 60, step=30),
    "24h": Window(seconds=24 * 60 * 60, step=600),
}

NET_DEVICES = 'job="node",device!~"lo|veth.*|docker.*|br-.*|virbr.*"'
CPU_QUERY = f"max by ({TARGET_LABEL}) (host:cpu_utilization:ratio_rate2m) * 100"
MEMORY_QUERY = f"max by ({TARGET_LABEL}) (1 - host:memory_available:ratio) * 100"
DISK_QUERY = f"max by ({TARGET_LABEL}) (1 - host:fs_avail:ratio) * 100"
NET_IN_QUERY = (
    f"sum by ({TARGET_LABEL}) (rate(node_network_receive_bytes_total{{{NET_DEVICES}}}[2m]))"
)
NET_OUT_QUERY = (
    f"sum by ({TARGET_LABEL}) (rate(node_network_transmit_bytes_total{{{NET_DEVICES}}}[2m]))"
)
NET_ERRORS_QUERY = (
    f"sum by ({TARGET_LABEL}) (rate({{__name__=~"
    f'"node_network_(receive|transmit)_(errs|drop)_total",{NET_DEVICES}}}[5m]))'
)
DISK_READ_QUERY = f'sum by ({TARGET_LABEL}) (rate(node_disk_read_bytes_total{{job="node"}}[2m]))'
DISK_WRITE_QUERY = (
    f'sum by ({TARGET_LABEL}) (rate(node_disk_written_bytes_total{{job="node"}}[2m]))'
)
LOAD_QUERY = f'max by ({TARGET_LABEL}) (node_load1{{job="node"}})'
NODE_JOB = 'job="node"'
UPTIME_QUERY = (
    f"max by ({TARGET_LABEL}) "
    f"(node_time_seconds{{{NODE_JOB}}} - node_boot_time_seconds{{{NODE_JOB}}})"
)
CPU_COUNT_QUERY = f'count by ({TARGET_LABEL}) (node_cpu_seconds_total{{job="node",mode="idle"}})'
SERVICE_UP_QUERY = f"max by ({TARGET_LABEL}, {RESOURCE_LABEL}) (noc_service_up)"
SERVICE_MEMORY_QUERY = f"max by ({TARGET_LABEL}, {RESOURCE_LABEL}) (noc_service_memory_bytes)"
SERVICE_LIMIT_QUERY = f"max by ({TARGET_LABEL}, {RESOURCE_LABEL}) (noc_service_memory_max_bytes)"

FLEET_QUERIES = (CPU_QUERY, MEMORY_QUERY, DISK_QUERY, NET_IN_QUERY, NET_OUT_QUERY)
SERVER_QUERIES = (
    CPU_QUERY,
    MEMORY_QUERY,
    DISK_QUERY,
    LOAD_QUERY,
    NET_IN_QUERY,
    NET_OUT_QUERY,
    NET_ERRORS_QUERY,
    DISK_READ_QUERY,
    DISK_WRITE_QUERY,
)


async def or_none[T](call: Awaitable[T]) -> T | None:
    try:
        return await call
    except PrometheusUnavailable:
        return None


def window_for(name: str) -> Window:
    return WINDOWS[name]


async def read_ranges(
    reader: PrometheusReader, queries: tuple[str, ...], window: Window, now: float
) -> list[list[Series] | None]:
    start = now - window.seconds
    return list(
        await asyncio.gather(
            *(or_none(reader.matrix(query, start, now, window.step)) for query in queries)
        )
    )


def points_for(series: list[Series] | None, name: str) -> list[Point]:
    for item in series or []:
        if item.labels.get(TARGET_LABEL) == name:
            return item.points
    return []


def value_for(samples: list[Sample] | None, name: str) -> float | None:
    for sample in samples or []:
        if sample.labels.get(TARGET_LABEL) == name:
            return sample.value
    return None


def any_answer(readings: list[list[Series] | None]) -> bool:
    return any(reading is not None for reading in readings)


def fleet_server(name: str, readings: list[list[Series] | None]) -> FleetServerLive:
    cpu, memory, disk, net_in, net_out = (points_for(reading, name) for reading in readings)
    return FleetServerLive(
        name=name, cpu=cpu, memory=memory, disk=disk, net_in=net_in, net_out=net_out
    )


def resource_name(resource_id: str) -> str:
    return resource_id.split(":", 1)[1] if ":" in resource_id else resource_id


def service_rows(
    name: str,
    up: list[Sample] | None,
    memory: list[Series] | None,
    limits: list[Sample] | None,
) -> list[ServiceLive]:
    own_up = {
        sample.labels.get(RESOURCE_LABEL, ""): sample.value
        for sample in up or []
        if sample.labels.get(TARGET_LABEL) == name
    }
    own_memory = {
        item.labels.get(RESOURCE_LABEL, ""): item.points
        for item in memory or []
        if item.labels.get(TARGET_LABEL) == name
    }
    own_limits = {
        sample.labels.get(RESOURCE_LABEL, ""): sample.value
        for sample in limits or []
        if sample.labels.get(TARGET_LABEL) == name
    }
    resources = sorted((set(own_up) | set(own_memory)) - {""})
    return [
        ServiceLive(
            resource_id=resource,
            name=resource_name(resource),
            up=None if resource not in own_up else own_up[resource] >= 1,
            memory_bytes=own_memory.get(resource, []),
            memory_limit_bytes=own_limits.get(resource),
        )
        for resource in resources
    ]


def whole_number(value: float | None) -> int | None:
    return None if value is None else int(value)


@router.get("/servers")
async def fleet_live(
    request: Request,
    session: Session,
    range_name: Annotated[LiveRange, Query(alias="range")] = "1h",
) -> FleetLive:
    reader: PrometheusReader = request.app.state.prometheus
    window = window_for(range_name)
    names = list(await session.scalars(select(Target.name).order_by(Target.name)))
    readings = await read_ranges(reader, FLEET_QUERIES, window, time.time())
    return FleetLive(
        range=range_name,
        step_seconds=window.step,
        available=any_answer(readings),
        servers=[fleet_server(name, readings) for name in names],
    )


@router.get("/servers/{server_id}")
async def server_live(
    server_id: uuid.UUID,
    request: Request,
    session: Session,
    range_name: Annotated[LiveRange, Query(alias="range")] = "1h",
) -> ServerLive:
    target = await session.get(Target, server_id)
    if target is None:
        raise HTTPException(404, "server not found")
    reader: PrometheusReader = request.app.state.prometheus
    window = window_for(range_name)
    now = time.time()
    readings, uptime, cpu_count, service_up, service_memory, service_limits = await asyncio.gather(
        read_ranges(reader, SERVER_QUERIES, window, now),
        or_none(reader.vector(UPTIME_QUERY)),
        or_none(reader.vector(CPU_COUNT_QUERY)),
        or_none(reader.vector(SERVICE_UP_QUERY)),
        or_none(reader.matrix(SERVICE_MEMORY_QUERY, now - window.seconds, now, window.step)),
        or_none(reader.vector(SERVICE_LIMIT_QUERY)),
    )
    name = target.name
    cpu, memory, disk, load, net_in, net_out, net_errors, disk_read, disk_write = (
        points_for(reading, name) for reading in readings
    )
    return ServerLive(
        range=range_name,
        step_seconds=window.step,
        available=any_answer(readings),
        cpu=cpu,
        memory=memory,
        disk=disk,
        load=load,
        net_in=net_in,
        net_out=net_out,
        net_errors=net_errors,
        disk_read=disk_read,
        disk_write=disk_write,
        uptime_seconds=value_for(uptime, name),
        cpu_count=whole_number(value_for(cpu_count, name)),
        services=service_rows(name, service_up, service_memory, service_limits),
    )
