import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, create_model
from sqlalchemy import select

from noc.db.models import ManagedResourceRow
from noc.db.session import SessionFactory
from noc.tools.spec import ToolContext, ToolOutput, ToolSpec
from noc_shared.permissions import PermissionClass
from noc_shared.resources import RESOURCE_ID_PATTERN, ResourceId
from noc_shared.tools import NoArgs

CATALOG_FILE = Path(__file__).with_name("promql_catalog.yaml")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
ALLOWED_PLACEHOLDERS = frozenset({"target", "resource"})
TARGET_NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
RESOURCE_ID_RE = re.compile(RESOURCE_ID_PATTERN)
QUERY_TIMEOUT_SECONDS = 10.0
MIN_STEP_SECONDS = 30
MAX_POINTS = 60
KEPT_LABELS = frozenset({"target", "resource", "mountpoint"})
WINDOW_SECONDS: dict[str, int] = {"15m": 900, "1h": 3600, "6h": 21600}
WindowName = Literal["15m", "1h", "6h"]
CATALOG_ADAPTER: TypeAdapter[dict[str, str]] = TypeAdapter(dict[str, str])


def load_catalog(path: Path = CATALOG_FILE) -> dict[str, str]:
    catalog = CATALOG_ADAPTER.validate_python(yaml.safe_load(path.read_text()))
    for name, template in catalog.items():
        unknown = set(PLACEHOLDER.findall(template)) - ALLOWED_PLACEHOLDERS
        if unknown or "{target}" not in template:
            raise ValueError(
                f"promql catalog query {name} may only use {{target}} and {{resource}}"
            )
    return catalog


def literal_of(values: tuple[str, ...]) -> Any:
    return cast(Any, Literal).__getitem__(values)


def render_promql(template: str, target: str, resource: str | None) -> str:
    rendered = template.replace("{target}", target)
    if resource is not None:
        rendered = rendered.replace("{resource}", resource)
    return rendered


CATALOG = load_catalog()
QUERY_NAMES = tuple(sorted(CATALOG))
OptionalResourceId = ResourceId | None

QueryNamedMetricArgs = create_model(
    "QueryNamedMetricArgs",
    __config__=ConfigDict(extra="forbid"),
    query=(
        literal_of(QUERY_NAMES),
        Field(description="Name of a catalogued host or service metric"),
    ),
    window=(WindowName, Field(default="1h", description="How far back to look")),
    resource_id=(
        OptionalResourceId,
        Field(
            default=None,
            description="Registered resource id, only for queries that are per resource",
        ),
    ),
)


class PrometheusError(Exception):
    pass


class PromSample(BaseModel):
    metric: dict[str, str] = Field(default_factory=dict)
    values: list[tuple[float, str]] = Field(default_factory=list)
    value: tuple[float, str] | None = None


class PromData(BaseModel):
    resultType: str
    result: list[PromSample] = Field(default_factory=list)


class PromEnvelope(BaseModel):
    status: str
    data: PromData | None = None
    error: str | None = None


class PrometheusClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def query_range(
        self, promql: str, start: float, end: float, step: int
    ) -> list[PromSample]:
        params = {"query": promql, "start": f"{start:.3f}", "end": f"{end:.3f}", "step": str(step)}
        return await self._get("/api/v1/query_range", params)

    async def query(self, promql: str, at: float) -> list[PromSample]:
        return await self._get("/api/v1/query", {"query": promql, "time": f"{at:.3f}"})

    async def _get(self, path: str, params: dict[str, str]) -> list[PromSample]:
        try:
            response = await self._http.get(
                self._base_url + path, params=params, timeout=QUERY_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            raise PrometheusError(f"{type(exc).__name__}: {exc}") from exc
        try:
            envelope = PromEnvelope.model_validate_json(response.content)
        except ValidationError as exc:
            raise PrometheusError(f"HTTP {response.status_code}, unreadable body") from exc
        if response.status_code >= 400 or envelope.status != "success" or envelope.data is None:
            raise PrometheusError(envelope.error or f"HTTP {response.status_code}")
        return envelope.data.result


class ResourceLookup(Protocol):
    async def resource_ids(self, target_id: uuid.UUID) -> frozenset[str]: ...


class DatabaseResourceLookup:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def resource_ids(self, target_id: uuid.UUID) -> frozenset[str]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(ManagedResourceRow.resource_id).where(
                    ManagedResourceRow.target_id == target_id
                )
            )
            return frozenset(result.all())


def finite(text: str) -> float | None:
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="seconds")


def series_summary(sample: PromSample) -> dict[str, Any] | None:
    points = [
        (timestamp, number)
        for timestamp, text in sample.values
        if (number := finite(text)) is not None
    ]
    if not points:
        return None
    numbers = [number for _, number in points]
    stride = math.ceil(len(points) / MAX_POINTS)
    return {
        "labels": {key: value for key, value in sample.metric.items() if key in KEPT_LABELS},
        "min": round(min(numbers), 6),
        "max": round(max(numbers), 6),
        "avg": round(sum(numbers) / len(numbers), 6),
        "last": round(numbers[-1], 6),
        "points": [
            {"at": iso(timestamp), "value": round(number, 6)}
            for timestamp, number in points[::stride]
        ],
    }


@dataclass(frozen=True)
class OverviewItem:
    key: str
    query: str
    worst_is_low: bool


HOST_OVERVIEW: tuple[OverviewItem, ...] = (
    OverviewItem("cpu_utilization", "cpu_usage", worst_is_low=False),
    OverviewItem("cpu_pressure_waiting", "cpu_pressure", worst_is_low=False),
    OverviewItem("memory_available", "memory_available", worst_is_low=True),
    OverviewItem("memory_pressure_stalled", "memory_pressure", worst_is_low=False),
    OverviewItem("fs_avail_min", "fs_avail", worst_is_low=True),
)


class PromQueries:
    def __init__(
        self, client: PrometheusClient, catalog: dict[str, str], resources: ResourceLookup
    ) -> None:
        self._client = client
        self._catalog = catalog
        self._resources = resources

    async def named_metric(self, args: BaseModel, context: ToolContext) -> ToolOutput:
        values = args.model_dump()
        target = context.target.name
        if TARGET_NAME_PATTERN.fullmatch(target) is None:
            return ToolOutput(ok=False, error="target name is not usable in a metric query")
        query_name = str(values["query"])
        template = self._catalog[query_name]
        resource_id: str | None = values["resource_id"]
        problem = await self._resource_problem(template, resource_id, context)
        if problem is not None:
            return ToolOutput(ok=False, error=problem)
        window = str(values["window"])
        window_seconds = WINDOW_SECONDS[window]
        step = max(MIN_STEP_SECONDS, window_seconds // 60)
        end = time.time()
        promql = render_promql(template, target, resource_id)
        try:
            samples = await self._client.query_range(promql, end - window_seconds, end, step)
        except PrometheusError as exc:
            return ToolOutput(ok=False, error=f"prometheus: {exc}")
        series = [summary for sample in samples if (summary := series_summary(sample)) is not None]
        return ToolOutput(
            ok=True,
            data={"query": query_name, "window": window, "step_seconds": step, "series": series},
        )

    async def host_overview(self, args: BaseModel, context: ToolContext) -> ToolOutput:
        target = context.target.name
        if TARGET_NAME_PATTERN.fullmatch(target) is None:
            return ToolOutput(ok=False, error="target name is not usable in a metric query")
        overview: dict[str, Any] = {"target": target}
        for item in HOST_OVERVIEW:
            try:
                overview[item.key] = await self._instant_worst(item, target)
            except PrometheusError as exc:
                return ToolOutput(ok=False, error=f"prometheus: {exc}")
        return ToolOutput(ok=True, data=overview)

    async def _instant_worst(self, item: OverviewItem, target: str) -> float | None:
        promql = render_promql(self._catalog[item.query], target, None)
        samples = await self._client.query(promql, time.time())
        numbers = [
            number
            for sample in samples
            if sample.value is not None and (number := finite(sample.value[1])) is not None
        ]
        if not numbers:
            return None
        worst = min(numbers) if item.worst_is_low else max(numbers)
        return round(worst, 6)

    async def _resource_problem(
        self, template: str, resource_id: str | None, context: ToolContext
    ) -> str | None:
        if "{resource}" not in template:
            return "this query does not take resource_id" if resource_id is not None else None
        if resource_id is None:
            return "this query needs a resource_id"
        if RESOURCE_ID_RE.fullmatch(resource_id) is None:
            return "resource_id has an invalid format"
        registered = await self._resources.resource_ids(context.target.id)
        if resource_id not in registered:
            return "resource_id is not registered for this target"
        return None


def build_prometheus_tools(
    client: PrometheusClient, resources: ResourceLookup, agents: frozenset[str]
) -> list[ToolSpec]:
    queries = PromQueries(client, CATALOG, resources)
    return [
        ToolSpec(
            name="query_named_metric",
            description=(
                "Read one named Prometheus metric for the incident's target over a window "
                "(15m, 1h or 6h): min, max, avg and last of each series plus up to 60 points. "
                "Only the query names in the schema exist. The target is fixed by the incident. "
                "Pass resource_id only for queries that are per resource."
            ),
            args_model=QueryNamedMetricArgs,
            permission=PermissionClass.READ_ONLY,
            agents=agents,
            handler=queries.named_metric,
        ),
        ToolSpec(
            name="get_host_overview",
            description=(
                "Read the current host health of the incident's target in one call: CPU "
                "utilisation, CPU and memory and I/O pressure, memory available ratio and the "
                "lowest filesystem free ratio. Values are null when the metric is missing."
            ),
            args_model=NoArgs,
            permission=PermissionClass.READ_ONLY,
            agents=agents,
            handler=queries.host_overview,
        ),
    ]
