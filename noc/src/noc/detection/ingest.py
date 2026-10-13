from datetime import datetime
from typing import Protocol

import structlog
from prometheus_client import Counter, Gauge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import AlertEvent, Incident
from noc.db.session import SessionFactory, transaction
from noc.detection.alerts import PrometheusAlert, PrometheusUnavailable
from noc.detection.correlator import correlate
from noc.detection.reconcile import OpenAlertState, plan_reconciliation
from noc.domain.incident_status import CLOSED_STATUSES
from noc.domain.severity import Severity

logger = structlog.get_logger(__name__)

POLL_ERRORS = Counter("noc_alert_poll_errors_total", "Failed Prometheus alert polls")
INGESTION_STALE = Gauge("noc_alert_ingestion_stale", "1 while the last alert poll failed")
LAST_POLL = Gauge("noc_alert_last_successful_poll_timestamp", "Unix time of last good poll")


class AlertSource(Protocol):
    async def firing_alerts(self) -> list[PrometheusAlert]: ...


class AlertIngestor:
    def __init__(
        self,
        source: AlertSource,
        sessions: SessionFactory,
        missing_polls_to_resolve: int,
    ) -> None:
        self._source = source
        self._sessions = sessions
        self._missing_polls_to_resolve = missing_polls_to_resolve

    async def poll_once(self) -> bool:
        try:
            firing = await self._source.firing_alerts()
        except PrometheusUnavailable as exc:
            POLL_ERRORS.inc()
            INGESTION_STALE.set(1)
            logger.warning("alert_poll_failed", error=str(exc))
            return False

        async with transaction(self._sessions) as session:
            await self._apply(session, firing, utc_now())

        INGESTION_STALE.set(0)
        LAST_POLL.set_to_current_time()
        return True

    async def _apply(
        self, session: AsyncSession, firing: list[PrometheusAlert], now: datetime
    ) -> None:
        open_rows = {
            row.fingerprint: row
            for row in await session.scalars(
                select(AlertEvent).where(AlertEvent.state == "firing").with_for_update()
            )
        }
        states = [OpenAlertState(fp, row.missed_polls) for fp, row in open_rows.items()]
        plan = plan_reconciliation(states, firing, self._missing_polls_to_resolve)

        for alert in plan.still_firing:
            row = open_rows[alert.fingerprint]
            row.last_seen_at = now
            row.missed_polls = 0
            row.value = alert.value
        await recorrelate_orphans(session, [open_rows[a.fingerprint] for a in plan.still_firing])

        for fingerprint in plan.missed:
            open_rows[fingerprint].missed_polls += 1

        for fingerprint in plan.resolved:
            row = open_rows[fingerprint]
            row.state = "resolved"
            row.ends_at = now

        for alert in plan.new:
            row = new_alert_event(alert, now)
            session.add(row)
            await session.flush()
            await correlate(session, row)


async def recorrelate_orphans(session: AsyncSession, rows: list[AlertEvent]) -> None:
    incident_ids = {row.incident_id for row in rows if row.incident_id is not None}
    closed_values = [status.value for status in CLOSED_STATUSES]
    closed = (
        set(
            await session.scalars(
                select(Incident.id).where(
                    Incident.id.in_(incident_ids), Incident.status.in_(closed_values)
                )
            )
        )
        if incident_ids
        else set()
    )
    for row in rows:
        if row.incident_id is None or row.incident_id in closed:
            row.incident_id = None
            await correlate(session, row)


def new_alert_event(alert: PrometheusAlert, now: datetime) -> AlertEvent:
    return AlertEvent(
        fingerprint=alert.fingerprint,
        alertname=alert.alertname,
        severity=Severity.parse(alert.labels.get("severity")).value,
        labels=alert.labels,
        annotations=alert.annotations,
        value=alert.value,
        state="firing",
        starts_at=alert.active_at,
        last_seen_at=now,
        missed_polls=0,
    )
