from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import WorkerHeartbeat


@dataclass
class PollStatus:
    last_ok_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None

    def ok(self, now: datetime) -> None:
        self.last_ok_at = now

    def failed(self, now: datetime, error: str) -> None:
        self.last_error = error
        self.last_error_at = now


def polling_is_fresh(poll: PollStatus, now: datetime, max_age: timedelta) -> bool:
    return poll.last_ok_at is not None and now - poll.last_ok_at <= max_age


def heartbeat_fields(poll: PollStatus, version: str, now: datetime) -> dict[str, Any]:
    return {
        "last_beat_at": now,
        "last_poll_ok_at": poll.last_ok_at,
        "last_poll_error": poll.last_error,
        "last_poll_error_at": poll.last_error_at,
        "version": version,
    }


async def write_heartbeat(
    session: AsyncSession,
    worker_id: str,
    started_at: datetime,
    poll: PollStatus,
    version: str,
    now: datetime,
) -> None:
    fields = heartbeat_fields(poll, version, now)
    statement = (
        insert(WorkerHeartbeat)
        .values(worker_id=worker_id, started_at=started_at, **fields)
        .on_conflict_do_update(index_elements=[WorkerHeartbeat.worker_id], set_=fields)
    )
    await session.execute(statement)
