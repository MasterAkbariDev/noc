import pytest
from sqlalchemy import select, text

from noc.db.models import Job
from noc.db.session import SessionFactory, transaction
from noc.jobs import queue

pytestmark = pytest.mark.integration


async def test_enqueue_is_deduplicated(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await queue.enqueue(session, "investigate", {"n": 1}, dedupe_key="investigate:x")
        await queue.enqueue(session, "investigate", {"n": 2}, dedupe_key="investigate:x")
    async with sessions() as session:
        assert len(list(await session.scalars(select(Job)))) == 1


async def test_a_job_is_claimed_by_one_worker_only(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await queue.enqueue(session, "investigate", {})
    async with transaction(sessions) as session:
        first = await queue.claim(session, "w1", ["investigate"], 60)
    async with transaction(sessions) as session:
        second = await queue.claim(session, "w2", ["investigate"], 60)
    assert first is not None
    assert second is None


async def test_expired_lease_is_reclaimed_and_old_owner_cannot_complete(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await queue.enqueue(session, "investigate", {})
    async with transaction(sessions) as session:
        job = await queue.claim(session, "w1", ["investigate"], 60)
        assert job is not None
        await session.execute(
            text("UPDATE jobs SET lease_expires_at = now() - interval '1 second'")
        )
    async with transaction(sessions) as session:
        reclaimed = await queue.claim(session, "w2", ["investigate"], 60)
    assert reclaimed is not None
    assert reclaimed.attempts == 2
    async with transaction(sessions) as session:
        assert not await queue.complete(session, job.id, "w1")
        assert await queue.complete(session, job.id, "w2")


async def test_failures_retry_then_go_dead(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await queue.enqueue(session, "investigate", {})
        await session.execute(text("UPDATE jobs SET max_attempts = 2"))
    for attempt in (1, 2):
        async with transaction(sessions) as session:
            job = await queue.claim(session, "w1", ["investigate"], 60)
            assert job is not None
            assert job.attempts == attempt
            await queue.fail(session, job.id, "w1", "boom", retry_delay_seconds=0)
    async with sessions() as session:
        assert await session.scalar(select(Job.status)) == "dead"
