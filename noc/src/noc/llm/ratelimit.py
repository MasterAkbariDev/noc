import asyncio
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from aiolimiter import AsyncLimiter
from sqlalchemy import text

from noc.db.session import SessionFactory, transaction
from noc.llm.client import QuotaExhausted

RESERVE_SQL = text(
    """
    INSERT INTO llm_quota_usage (provider, model, day, requests)
    VALUES (:provider, :model, :day, 1)
    ON CONFLICT (provider, model, day) DO UPDATE
       SET requests = llm_quota_usage.requests + 1
     WHERE llm_quota_usage.requests < :limit
    RETURNING requests
    """
)


class QuotaStore(Protocol):
    async def reserve(self, provider: str, model: str, day: date, limit: int) -> bool: ...


class MemoryQuotaStore:
    def __init__(self) -> None:
        self._used: defaultdict[tuple[str, str, date], int] = defaultdict(int)

    async def reserve(self, provider: str, model: str, day: date, limit: int) -> bool:
        key = (provider, model, day)
        if self._used[key] >= limit:
            return False
        self._used[key] += 1
        return True


class PostgresQuotaStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def reserve(self, provider: str, model: str, day: date, limit: int) -> bool:
        async with transaction(self._sessions) as session:
            result = await session.execute(
                RESERVE_SQL,
                {"provider": provider, "model": model, "day": day, "limit": limit},
            )
            return result.first() is not None


class RequestBudget:
    def __init__(
        self,
        provider: str,
        model: str,
        requests_per_minute: int,
        requests_per_day: int,
        quota_timezone: str,
        quota_store: QuotaStore,
    ) -> None:
        self.provider = provider
        self.model = model
        self._per_minute = AsyncLimiter(requests_per_minute, 60)
        self._per_day = requests_per_day
        self._zone = ZoneInfo(quota_timezone)
        self._store = quota_store

    def quota_day(self) -> date:
        return datetime.now(self._zone).date()

    async def acquire(self, deadline_seconds: float) -> int:
        reserved = await self._store.reserve(
            self.provider, self.model, self.quota_day(), self._per_day
        )
        if not reserved:
            raise QuotaExhausted(f"{self.provider}/{self.model} daily quota used up")
        started = time.monotonic()
        async with asyncio.timeout(deadline_seconds):
            await self._per_minute.acquire()
        return int((time.monotonic() - started) * 1000)
