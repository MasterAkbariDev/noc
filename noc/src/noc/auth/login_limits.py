from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noc.db.models import LoginFailure

USERNAME_LIMIT = 5
DEFAULT_IP_LIMIT = 20
WINDOW = timedelta(minutes=15)
USERNAME_MAX_LENGTH = 64


async def count_recent(session: AsyncSession, now: datetime, criterion: ColumnElement[bool]) -> int:
    statement = (
        select(func.count())
        .select_from(LoginFailure)
        .where(LoginFailure.ts >= now - WINDOW, criterion)
    )
    return int(await session.scalar(statement) or 0)


async def over_limit(
    session: AsyncSession, username: str, ip: str, now: datetime, ip_limit: int = DEFAULT_IP_LIMIT
) -> bool:
    attempts_for_user = await count_recent(session, now, LoginFailure.username == username)
    if attempts_for_user > USERNAME_LIMIT:
        return True
    if ip_limit <= 0:
        return False
    attempts_from_ip = await count_recent(session, now, LoginFailure.ip == ip)
    return attempts_from_ip > ip_limit


async def record_attempt(session: AsyncSession, username: str, ip: str, now: datetime) -> int:
    attempt = LoginFailure(username=username[:USERNAME_MAX_LENGTH], ip=ip, ts=now)
    session.add(attempt)
    await session.flush()
    await prune(session, now)
    await session.commit()
    return attempt.id


async def drop_attempt(session: AsyncSession, attempt_id: int) -> None:
    await session.execute(delete(LoginFailure).where(LoginFailure.id == attempt_id))
    await session.commit()


async def clear_failures(session: AsyncSession, username: str) -> int:
    result = await session.execute(delete(LoginFailure).where(LoginFailure.username == username))
    return int(getattr(result, "rowcount", 0) or 0)


async def prune(session: AsyncSession, now: datetime) -> None:
    await session.execute(delete(LoginFailure).where(LoginFailure.ts < now - WINDOW))
