import pytest
from sqlalchemy import func, select

from noc.db.models import AlertEvent, Incident, Job
from noc.db.session import SessionFactory, transaction
from noc.detection.alerts import PrometheusAlert, PrometheusUnavailable
from noc.detection.ingest import AlertIngestor
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration


class StaticAlertSource:
    def __init__(self) -> None:
        self.alerts: list[PrometheusAlert] = []
        self.failing = False

    async def firing_alerts(self) -> list[PrometheusAlert]:
        if self.failing:
            raise PrometheusUnavailable("down")
        return list(self.alerts)


async def register_demo_target(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )


async def count(sessions: SessionFactory, model: type) -> int:
    async with sessions() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
async def ingestor(sessions: SessionFactory) -> tuple[AlertIngestor, StaticAlertSource]:
    await register_demo_target(sessions)
    source = StaticAlertSource()
    return AlertIngestor(source, sessions, missing_polls_to_resolve=2), source


async def test_repeated_polls_create_one_incident_and_one_job(
    sessions: SessionFactory, ingestor: tuple[AlertIngestor, StaticAlertSource]
) -> None:
    poller, source = ingestor
    source.alerts = [prometheus_alert()]
    for _ in range(3):
        assert await poller.poll_once()
    assert await count(sessions, Incident) == 1
    assert await count(sessions, Job) == 1
    assert await count(sessions, AlertEvent) == 1


async def test_second_alert_attaches_and_raises_severity(
    sessions: SessionFactory, ingestor: tuple[AlertIngestor, StaticAlertSource]
) -> None:
    poller, source = ingestor
    source.alerts = [prometheus_alert(alertname="HostHighCPU", severity="warning")]
    await poller.poll_once()
    source.alerts.append(prometheus_alert())
    await poller.poll_once()
    async with sessions() as session:
        incident = await session.scalar(select(Incident))
        assert incident is not None
        assert incident.severity == "critical"
    assert await count(sessions, Incident) == 1
    assert await count(sessions, AlertEvent) == 2


async def test_failed_poll_never_counts_as_recovery(
    sessions: SessionFactory, ingestor: tuple[AlertIngestor, StaticAlertSource]
) -> None:
    poller, source = ingestor
    source.alerts = [prometheus_alert()]
    await poller.poll_once()
    source.failing = True
    for _ in range(3):
        assert not await poller.poll_once()
    async with sessions() as session:
        assert await session.scalar(select(AlertEvent.state)) == "firing"


async def test_alert_resolves_after_two_missing_polls(
    sessions: SessionFactory, ingestor: tuple[AlertIngestor, StaticAlertSource]
) -> None:
    poller, source = ingestor
    source.alerts = [prometheus_alert()]
    await poller.poll_once()
    source.alerts = []
    await poller.poll_once()
    async with sessions() as session:
        assert await session.scalar(select(AlertEvent.state)) == "firing"
    await poller.poll_once()
    async with sessions() as session:
        assert await session.scalar(select(AlertEvent.state)) == "resolved"


async def test_unknown_targets_and_info_alerts_open_no_incident(
    sessions: SessionFactory, ingestor: tuple[AlertIngestor, StaticAlertSource]
) -> None:
    poller, source = ingestor
    source.alerts = [prometheus_alert(target="stranger"), prometheus_alert(severity="info")]
    await poller.poll_once()
    assert await count(sessions, Incident) == 0
    assert await count(sessions, AlertEvent) == 2
