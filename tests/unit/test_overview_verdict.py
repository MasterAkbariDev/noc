import uuid
from datetime import UTC, datetime

import pytest

from noc.api.overview import key_is_working, llm_keys_working, overview_verdict
from noc.api.schemas import (
    ComponentHealth,
    ComponentStatus,
    Kpis,
    LlmKeyView,
    LlmStatus,
    OverviewVerdict,
    ServerStatus,
    ServerSummary,
    SystemHealth,
    Verdict,
)

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def component(
    key: str, label: str, status: ComponentStatus, summary: str = "Fine"
) -> ComponentHealth:
    return ComponentHealth(
        key=key, label=label, status=status, summary=summary, details={}, since=None
    )


def healthy_components() -> list[ComponentHealth]:
    return [
        component("worker", "Worker", "ok", "Last heartbeat 5 s ago"),
        component("alert_polling", "Alert polling", "ok", "Last alert poll succeeded 3 s ago"),
        component("prometheus", "Prometheus", "ok", "All 2 scrape targets are up"),
    ]


def health(verdict: Verdict, components: list[ComponentHealth]) -> SystemHealth:
    return SystemHealth(verdict=verdict, checked_at=NOW, components=components, stuck_incidents=[])


def server(name: str, status: ServerStatus, halted: bool = False) -> ServerSummary:
    return ServerSummary(
        id=uuid.uuid4(),
        name=name,
        environment="lab",
        automation_level="observe_only",
        automation_label="Watch only",
        halted=halted,
        status=status,
        last_scrape_at=None,
        metrics=None,
        open_incidents=0,
        worst_severity=None,
        headline="Healthy",
    )


def kpis(
    needs_you: int = 0, open_incidents: int = 0, servers_up: int = 1, servers_total: int = 1
) -> Kpis:
    return Kpis(
        open_incidents=open_incidents,
        needs_you=needs_you,
        servers_up=servers_up,
        servers_total=servers_total,
        llm_keys_ok=1,
        llm_keys_total=1,
    )


def llm_status(mode: str, *states: str) -> LlmStatus:
    keys = [
        LlmKeyView(
            label=f"gemini#{index}",
            provider="gemini",
            state=state,
            cooling_until=None,
            last_error=None,
            last_error_at=None,
            last_success_at=None,
            models=[],
        )
        for index, state in enumerate(states)
    ]
    return LlmStatus(mode=mode, keys=keys)


def test_a_down_core_component_makes_the_verdict_down() -> None:
    components = [
        component("worker", "Worker", "down", "The worker has never reported"),
        component("prometheus", "Prometheus", "ok", "All 2 scrape targets are up"),
    ]
    verdict = overview_verdict(health("down", components), kpis(), 0, [], True)
    assert verdict == OverviewVerdict(
        level="down", sentence="The NOC is not working: The worker has never reported"
    )


def test_incidents_that_need_a_person_make_the_verdict_attention() -> None:
    verdict = overview_verdict(health("ok", healthy_components()), kpis(needs_you=1), 0, [], True)
    assert verdict == OverviewVerdict(level="attention", sentence="1 incident needs you")


def test_the_attention_sentence_counts_several_incidents() -> None:
    verdict = overview_verdict(health("ok", healthy_components()), kpis(needs_you=3), 0, [], True)
    assert verdict == OverviewVerdict(level="attention", sentence="3 incidents need you")


def test_attention_names_the_noc_problem_as_well_when_there_is_one() -> None:
    components = [
        component("worker", "Worker", "degraded", "Last heartbeat 6 min ago"),
        component("alert_polling", "Alert polling", "ok", "Last alert poll succeeded 3 s ago"),
    ]
    verdict = overview_verdict(health("degraded", components), kpis(needs_you=1), 1, [], True)
    assert verdict == OverviewVerdict(
        level="attention", sentence="1 incident needs you · Worker: Last heartbeat 6 min ago"
    )


def test_a_degraded_component_names_the_first_problem() -> None:
    components = [
        component("worker", "Worker", "ok", "Last heartbeat 5 s ago"),
        component("alert_polling", "Alert polling", "degraded", "No alert poll has succeeded yet"),
        component("prometheus", "Prometheus", "down", "Prometheus cannot be reached"),
    ]
    verdict = overview_verdict(health("degraded", components), kpis(), 0, [], True)
    assert verdict == OverviewVerdict(
        level="degraded", sentence="Alert polling: No alert poll has succeeded yet"
    )


def test_a_server_that_is_down_makes_the_verdict_degraded() -> None:
    servers = [server("alpha-1", "up"), server("zeta-2", "down")]
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 0, servers, True)
    assert verdict == OverviewVerdict(level="degraded", sentence="zeta-2 is not reachable")


def test_a_server_with_unknown_status_makes_the_verdict_degraded() -> None:
    servers = [server("alpha-1", "up"), server("zeta-2", "unknown")]
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 0, servers, True)
    assert verdict == OverviewVerdict(level="degraded", sentence="zeta-2 status is unknown")


def test_a_halted_server_makes_the_verdict_degraded() -> None:
    servers = [server("alpha-1", "up", halted=True)]
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 0, servers, True)
    assert verdict == OverviewVerdict(level="degraded", sentence="alpha-1 is halted")


def test_no_working_llm_key_makes_the_verdict_degraded() -> None:
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 0, [], False)
    assert verdict == OverviewVerdict(level="degraded", sentence="No AI model key is working")


def test_a_problem_beats_a_running_incident() -> None:
    servers = [server("zeta-2", "down")]
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 1, servers, True)
    assert verdict == OverviewVerdict(level="degraded", sentence="zeta-2 is not reachable")


def test_a_running_incident_makes_the_verdict_working() -> None:
    servers = [server("alpha-1", "up"), server("zeta-2", "up")]
    verdict = overview_verdict(
        health("ok", healthy_components()), kpis(servers_up=2, servers_total=2), 1, servers, True
    )
    assert verdict == OverviewVerdict(
        level="working", sentence="Working on 1 incident · 2 servers up · LLM OK"
    )


def test_the_working_sentence_counts_several_incidents() -> None:
    servers = [server("alpha-1", "up")]
    verdict = overview_verdict(health("ok", healthy_components()), kpis(), 3, servers, True)
    assert verdict == OverviewVerdict(
        level="working", sentence="Working on 3 incidents · 1 server up · LLM OK"
    )


def test_a_quiet_fleet_says_ok_with_the_summary_line() -> None:
    verdict = overview_verdict(
        health("ok", healthy_components()),
        kpis(open_incidents=1, servers_up=2, servers_total=2),
        0,
        [server("alpha-1", "up"), server("zeta-2", "up")],
        True,
    )
    assert verdict == OverviewVerdict(level="ok", sentence="2 servers · 1 open incident · LLM OK")


def test_the_ok_summary_uses_singular_and_plural_counts() -> None:
    verdict = overview_verdict(
        health("ok", healthy_components()), kpis(), 0, [server("a", "up")], True
    )
    assert verdict == OverviewVerdict(level="ok", sentence="1 server · 0 open incidents · LLM OK")


@pytest.mark.parametrize(
    ("state", "mode", "expected"),
    [
        ("ok", "live", True),
        ("unused", "live", True),
        ("cooling", "live", False),
        ("rejected", "record", False),
        ("cooling", "replay", True),
        ("rejected", "replay", True),
    ],
)
def test_a_key_counts_as_working_unless_it_is_cooling_or_rejected_outside_replay(
    state: str, mode: str, expected: bool
) -> None:
    assert key_is_working(state, mode) is expected


def test_only_working_keys_are_counted() -> None:
    assert llm_keys_working(llm_status("live", "ok", "cooling", "unused")) == 2


def test_replay_counts_every_key_as_working() -> None:
    assert llm_keys_working(llm_status("replay", "cooling", "rejected")) == 2
