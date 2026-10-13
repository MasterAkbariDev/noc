from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import Job

CLAIM_SQL = text(
    """
    UPDATE jobs
       SET status = 'running',
           attempts = attempts + 1,
           locked_by = :worker,
           lease_expires_at = now() + make_interval(secs => :lease)
     WHERE id = (
           SELECT id FROM jobs
            WHERE kind = ANY(:kinds)
              AND ((status = 'queued' AND run_after <= now())
                OR (status = 'running' AND lease_expires_at < now()))
            ORDER BY priority DESC, id
            FOR UPDATE SKIP LOCKED
            LIMIT 1)
    RETURNING id, kind, payload, attempts, max_attempts
    """
)

HEARTBEAT_SQL = text(
    """
    UPDATE jobs SET lease_expires_at = now() + make_interval(secs => :lease)
     WHERE id = :job_id AND locked_by = :worker AND status = 'running'
    """
)

COMPLETE_SQL = text(
    """
    UPDATE jobs SET status = 'done', finished_at = now(), lease_expires_at = NULL
     WHERE id = :job_id AND locked_by = :worker AND status = 'running'
    """
)

FAIL_SQL = text(
    """
    UPDATE jobs
       SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
           run_after = now() + make_interval(secs => :retry_delay),
           last_error = :error,
           lease_expires_at = NULL,
           locked_by = NULL
     WHERE id = :job_id AND locked_by = :worker AND status = 'running'
    """
)


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    dedupe_key: str | None = None,
    priority: int = 0,
) -> None:
    statement = (
        insert(Job)
        .values(kind=kind, payload=payload, dedupe_key=dedupe_key, priority=priority)
        .on_conflict_do_nothing(index_elements=[Job.dedupe_key])
    )
    await session.execute(statement)


async def claim(
    session: AsyncSession, worker: str, kinds: list[str], lease_seconds: int
) -> ClaimedJob | None:
    result = await session.execute(
        CLAIM_SQL, {"worker": worker, "kinds": kinds, "lease": lease_seconds}
    )
    row = result.mappings().first()
    return ClaimedJob(**row) if row else None


async def changed_rows(session: AsyncSession, statement: Any, parameters: dict[str, Any]) -> int:
    result = cast(CursorResult[Any], await session.execute(statement, parameters))
    return result.rowcount


async def heartbeat(session: AsyncSession, job_id: int, worker: str, lease_seconds: int) -> bool:
    parameters = {"job_id": job_id, "worker": worker, "lease": lease_seconds}
    return await changed_rows(session, HEARTBEAT_SQL, parameters) == 1


async def complete(session: AsyncSession, job_id: int, worker: str) -> bool:
    return await changed_rows(session, COMPLETE_SQL, {"job_id": job_id, "worker": worker}) == 1


async def fail(
    session: AsyncSession, job_id: int, worker: str, error: str, retry_delay_seconds: int
) -> bool:
    parameters = {
        "job_id": job_id,
        "worker": worker,
        "error": error,
        "retry_delay": retry_delay_seconds,
    }
    return await changed_rows(session, FAIL_SQL, parameters) == 1


async def is_dead(session: AsyncSession, job_id: int) -> bool:
    status = await session.scalar(select(Job.status).where(Job.id == job_id))
    return status == "dead"
