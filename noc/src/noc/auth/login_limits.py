from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noc.db.models import LoginFailure

USERNAME_LIMIT = 5
IP_LIMIT = 20
WINDOW = timedelta(minutes=15)
USERNAME_MAX_LENGTH = 64


async def count_recent(session: AsyncSession, now: datetime, criterion: ColumnElement[bool]) -> int:
    statement = (
        select(func.count())
        .select_from(LoginFailure)
        .where(LoginFailure.ts >= now - WINDOW, criterion)
    )
    return int(await session.scalar(statement) or 0)


async def is_blocked(session: AsyncSession, username: str, ip: str, now: datetime) -> bool:
    failures_for_user = await count_recent(session, now, LoginFailure.username == username)
    if failures_for_user >= USERNAME_LIMIT:
        return True
    failures_from_ip = await count_recent(session, now, LoginFailure.ip == ip)
    return failures_from_ip >= IP_LIMIT


async def record_failure(session: AsyncSession, username: str, ip: str, now: datetime) -> None:
    session.add(LoginFailure(username=username[:USERNAME_MAX_LENGTH], ip=ip, ts=now))
    await session.flush()
    await prune(session, now)


async def prune(session: AsyncSession, now: datetime) -> None:
    await session.execute(delete(LoginFailure).where(LoginFailure.ts < now - WINDOW))
