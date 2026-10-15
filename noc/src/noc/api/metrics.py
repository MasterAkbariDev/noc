import statistics
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.auth.roles import Role
from noc.db.base import utc_now
from noc.db.models import ActionRow, Incident, LlmCall, ToolCall

TOP_CATEGORIES: Final = 8
OTHER: Final = "other"
UNDIAGNOSED: Final = "not diagnosed"
SECONDS_PER_MINUTE: Final = 60
EXECUTED_ACTIONS: Final = ("succeeded", "failed", "outcome_unknown")

router = APIRouter(
    prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]


class DayPoint(BaseModel):
    day: date
    opened: int = 0
    resolved: int = 0
    escalated: int = 0
    llm_calls: int = 0
    tokens: int = 0
    tool_calls: int = 0


class CategoryCount(BaseModel):
    label: str
    count: int


class VariantRow(BaseModel):
    variant: str
    incidents: int
    resolved: int
    escalated: int
    llm_calls: int


class Totals(BaseModel):
    incidents: int
    resolved: int
    escalated: int
    open: int
    auto_resolved_share: float | None
    median_minutes_to_resolve: float | None
    median_minutes_to_diagnose: float | None
    llm_calls: int
    llm_failures: int
    tokens: int
    tool_calls: int
    actions_run: int
    reviewed: int
    confirmed: int


class MetricsView(BaseModel):
    days: int
    since: datetime
    totals: Totals
    per_day: list[DayPoint]
    root_causes: list[CategoryCount]
    outcomes: list[CategoryCount]
    actions: list[CategoryCount]
    variants: list[VariantRow]


def day_series(since: datetime, days: int) -> dict[date, DayPoint]:
    first = since.date()
    return {
        first + timedelta(days=offset): DayPoint(day=first + timedelta(days=offset))
        for offset in range(days)
    }


def top_with_other(counts: dict[str, int]) -> list[CategoryCount]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    head = [CategoryCount(label=label, count=count) for label, count in ranked[:TOP_CATEGORIES]]
    tail = sum(count for _, count in ranked[TOP_CATEGORIES:])
    if tail:
        head.append(CategoryCount(label=OTHER, count=tail))
    return head


def was_reviewed(incident: Incident) -> bool:
    return incident.closed_at is not None and bool(incident.resolution_note)


def was_confirmed(incident: Incident) -> bool:
    corrected = incident.corrected_root_cause_code
    return corrected is None or corrected == incident.root_cause_code


def minutes_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / SECONDS_PER_MINUTE


def median_or_none(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


async def daily_counts(session: AsyncSession, column: Any, since: datetime) -> dict[date, int]:
    day = cast(column, Date)
    rows = await session.execute(select(day, func.count()).where(column >= since).group_by(day))
    return {bucket: count for bucket, count in rows.all()}


async def daily_llm(session: AsyncSession, since: datetime) -> dict[date, tuple[int, int, int]]:
    day = cast(LlmCall.created_at, Date)
    failed = func.count().filter(LlmCall.error.is_not(None))
    tokens = func.coalesce(func.sum(LlmCall.tokens_in + LlmCall.tokens_out), 0)
    rows = await session.execute(
        select(day, func.count(), failed, tokens).where(LlmCall.created_at >= since).group_by(day)
    )
    return {bucket: (calls, failures, int(used)) for bucket, calls, failures, used in rows.all()}


async def llm_calls_by_incident(session: AsyncSession, since: datetime) -> dict[Any, int]:
    rows = await session.execute(
        select(LlmCall.incident_id, func.count())
        .where(LlmCall.created_at >= since, LlmCall.incident_id.is_not(None))
        .group_by(LlmCall.incident_id)
    )
    return {incident_id: count for incident_id, count in rows.all()}


def variant_rows(incidents: list[Incident], calls: dict[Any, int]) -> list[VariantRow]:
    grouped: dict[str, list[Incident]] = defaultdict(list)
    for incident in incidents:
        grouped[incident.mode].append(incident)
    return [
        VariantRow(
            variant=variant,
            incidents=len(items),
            resolved=sum(1 for item in items if item.resolved_at is not None),
            escalated=sum(1 for item in items if item.escalated_at is not None),
            llm_calls=sum(calls.get(item.id, 0) for item in items),
        )
        for variant, items in sorted(grouped.items())
    ]


@router.get("")
async def get_metrics(
    session: Session, days: Annotated[int, Query(ge=1, le=90)] = 14
) -> MetricsView:
    now = utc_now()
    since = datetime.combine(
        (now - timedelta(days=days - 1)).date(), datetime.min.time(), now.tzinfo
    )
    series = day_series(since, days)
    for bucket, count in (await daily_counts(session, Incident.opened_at, since)).items():
        series[bucket].opened = count
    for bucket, count in (await daily_counts(session, Incident.resolved_at, since)).items():
        series[bucket].resolved = count
    for bucket, count in (await daily_counts(session, Incident.escalated_at, since)).items():
        series[bucket].escalated = count
    for bucket, count in (await daily_counts(session, ToolCall.started_at, since)).items():
        series[bucket].tool_calls = count
    llm = await daily_llm(session, since)
    for bucket, (calls, _, used) in llm.items():
        series[bucket].llm_calls = calls
        series[bucket].tokens = used

    incidents = list(await session.scalars(select(Incident).where(Incident.opened_at >= since)))
    resolved = [item for item in incidents if item.resolved_at is not None]
    escalated = [item for item in incidents if item.escalated_at is not None]
    open_now = [item for item in incidents if item.closed_at is None and item.resolved_at is None]
    resolve_minutes = [
        m for m in (minutes_between(i.opened_at, i.resolved_at) for i in resolved) if m is not None
    ]
    diagnose_minutes = [
        m
        for m in (minutes_between(i.opened_at, i.diagnosed_at) for i in incidents)
        if m is not None
    ]
    actions = await session.execute(
        select(ActionRow.status, func.count())
        .where(ActionRow.created_at >= since)
        .group_by(ActionRow.status)
    )
    action_counts = {status: count for status, count in actions.all()}
    finished = len(resolved) + len(escalated)
    reviewed = [item for item in incidents if was_reviewed(item)]

    return MetricsView(
        days=days,
        since=since,
        totals=Totals(
            incidents=len(incidents),
            resolved=len(resolved),
            escalated=len(escalated),
            open=len(open_now),
            auto_resolved_share=round(len(resolved) / finished, 3) if finished else None,
            median_minutes_to_resolve=median_or_none(resolve_minutes),
            median_minutes_to_diagnose=median_or_none(diagnose_minutes),
            llm_calls=sum(calls for calls, _, _ in llm.values()),
            llm_failures=sum(failures for _, failures, _ in llm.values()),
            tokens=sum(used for _, _, used in llm.values()),
            tool_calls=sum(point.tool_calls for point in series.values()),
            actions_run=sum(action_counts.get(status, 0) for status in EXECUTED_ACTIONS),
            reviewed=len(reviewed),
            confirmed=sum(1 for item in reviewed if was_confirmed(item)),
        ),
        per_day=list(series.values()),
        root_causes=top_with_other(
            count_values(item.root_cause_code or UNDIAGNOSED for item in incidents)
        ),
        outcomes=top_with_other(count_values(item.status for item in incidents)),
        actions=top_with_other(action_counts),
        variants=variant_rows(incidents, await llm_calls_by_incident(session, since)),
    )


def count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return dict(counts)
