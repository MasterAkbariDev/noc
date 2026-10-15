from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from noc.api.app import create_app
from noc.api.metrics import CategoryCount, top_with_other
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import ActionRow, Incident, LlmCall, ToolCall
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
async def client(sessions: SessionFactory) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(TOKEN), _env_file=None)
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


def incident(target_id: object, opened: datetime, **fields: object) -> Incident:
    values: dict[str, object] = {
        "target_id": target_id,
        "status": "RESOLVED",
        "severity": "critical",
        "title": "ServiceDown on demo-1",
        "trace_id": "a" * 32,
        "opened_at": opened,
        "mode": "multi",
    }
    values.update(fields)
    return Incident(**values)


def llm_call(incident_id: object, at: datetime, error: str | None = None) -> LlmCall:
    return LlmCall(
        incident_id=incident_id,
        agent="metrics",
        tier="small",
        provider="groq",
        model="m",
        mode="live",
        request_hash="h" * 64,
        tokens_in=100,
        tokens_out=20,
        created_at=at,
        error=error,
    )


def tool_call(incident_id: object, at: datetime) -> ToolCall:
    return ToolCall(
        ref="T1",
        incident_id=incident_id,
        agent="metrics",
        tool="get_service_status",
        args={},
        permission="read",
        decision="allowed",
        ok=True,
        started_at=at,
        duration_ms=5,
        result_sha256="0" * 64,
    )


def action(incident_id: object, target_id: object, status: str, at: datetime) -> ActionRow:
    return ActionRow(
        incident_id=incident_id,
        target_id=target_id,
        action_type="restart_service",
        resource_id="svc:demo-shop",
        params={},
        status=status,
        permission_class="SAFE_ACTION",
        eligible=True,
        auto_executable=True,
        gate_failures=[],
        reasons=[],
        impact_score=2,
        policy_version="t",
        action_hash=status.ljust(64, "x")[:64],
        created_at=at,
    )


@pytest.fixture
async def history(sessions: SessionFactory) -> datetime:
    now = utc_now()
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if today > now:
        today -= timedelta(days=1)
    yesterday = today - timedelta(days=1)
    async with transaction(sessions) as session:
        target = await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        fixed = incident(
            target.id,
            yesterday,
            resolved_at=yesterday + timedelta(minutes=10),
            diagnosed_at=yesterday + timedelta(minutes=2),
            root_cause_code="service_crashed",
            closed_at=None,
        )
        handed_over = incident(
            target.id,
            today - timedelta(hours=1),
            status="ESCALATED",
            escalated_at=today - timedelta(minutes=50),
            diagnosed_at=today - timedelta(minutes=56),
            root_cause_code="unknown",
            mode="runbook",
        )
        old = incident(
            target.id, today - timedelta(days=40), resolved_at=today - timedelta(days=40)
        )
        session.add_all([fixed, handed_over, old])
        await session.flush()
        session.add_all(
            [
                llm_call(fixed.id, yesterday),
                llm_call(fixed.id, yesterday, error="ProviderUnavailable"),
                llm_call(handed_over.id, today - timedelta(minutes=55)),
                tool_call(fixed.id, yesterday),
                tool_call(handed_over.id, today - timedelta(minutes=55)),
                action(fixed.id, target.id, "succeeded", yesterday),
                action(handed_over.id, target.id, "refused", today - timedelta(minutes=50)),
            ]
        )
    return today


async def test_metrics_need_a_viewer(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/metrics")).status_code == 401


@pytest.mark.usefixtures("history")
async def test_totals_cover_only_the_chosen_window(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/metrics?days=7", headers=AUTH)).json()
    totals = body["totals"]
    assert body["days"] == 7
    assert len(body["per_day"]) == 7
    assert totals["incidents"] == 2
    assert totals["resolved"] == 1
    assert totals["escalated"] == 1
    assert totals["auto_resolved_share"] == 0.5
    assert totals["median_minutes_to_resolve"] == 10.0
    assert totals["median_minutes_to_diagnose"] == 3.0
    assert totals["llm_calls"] == 3
    assert totals["llm_failures"] == 1
    assert totals["tokens"] == 360
    assert totals["tool_calls"] == 2
    assert totals["actions_run"] == 1


async def test_days_are_bucketed_with_empty_days_filled(
    client: httpx.AsyncClient, history: datetime
) -> None:
    body = (await client.get("/api/metrics?days=3", headers=AUTH)).json()
    points = {point["day"]: point for point in body["per_day"]}
    today = history.date().isoformat()
    yesterday = (history - timedelta(days=1)).date().isoformat()
    assert list(points) == sorted(points)
    assert points[yesterday]["opened"] == 1
    assert points[yesterday]["resolved"] == 1
    assert points[yesterday]["llm_calls"] == 2
    assert points[today]["escalated"] == 1
    assert points[today]["tool_calls"] == 1
    quiet = [point for day, point in points.items() if day not in (today, yesterday)]
    assert quiet
    assert all(point["opened"] == 0 and point["llm_calls"] == 0 for point in quiet)


@pytest.mark.usefixtures("history")
async def test_categories_and_variants(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/metrics?days=7", headers=AUTH)).json()
    assert {(c["label"], c["count"]) for c in body["root_causes"]} == {
        ("service_crashed", 1),
        ("unknown", 1),
    }
    assert {(c["label"], c["count"]) for c in body["outcomes"]} == {
        ("RESOLVED", 1),
        ("ESCALATED", 1),
    }
    assert {(c["label"], c["count"]) for c in body["actions"]} == {("succeeded", 1), ("refused", 1)}
    assert body["variants"] == [
        {"variant": "multi", "incidents": 1, "resolved": 1, "escalated": 0, "llm_calls": 2},
        {"variant": "runbook", "incidents": 1, "resolved": 0, "escalated": 1, "llm_calls": 1},
    ]


async def test_window_bounds_are_checked(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/metrics?days=0", headers=AUTH)).status_code == 422
    assert (await client.get("/api/metrics?days=91", headers=AUTH)).status_code == 422


async def test_an_empty_database_gives_zeros_not_errors(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/metrics", headers=AUTH)).json()
    assert body["totals"]["incidents"] == 0
    assert body["totals"]["auto_resolved_share"] is None
    assert body["totals"]["median_minutes_to_resolve"] is None
    assert len(body["per_day"]) == 14


def test_categories_beyond_eight_fold_into_other() -> None:
    counts = {f"cause_{index}": 10 - index for index in range(10)}
    folded = top_with_other(counts)
    assert len(folded) == 9
    assert folded[-1] == CategoryCount(label="other", count=2 + 1)
    assert folded[0] == CategoryCount(label="cause_0", count=10)
