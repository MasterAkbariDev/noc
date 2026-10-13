import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuthSession, User

SESSION_COOKIE = "noc_session"
CSRF_COOKIE = "noc_csrf"
CSRF_HEADER = "X-CSRF-Token"
TOUCH_AFTER = timedelta(seconds=60)


@dataclass(frozen=True)
class NewSession:
    token: str
    csrf_token: str
    row: AuthSession


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def is_expired(row: AuthSession, settings: Settings, now: datetime) -> bool:
    idle_deadline = row.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    return now >= row.expires_at or now >= idle_deadline


async def create_session(
    session: AsyncSession, user: User, ip: str, settings: Settings
) -> NewSession:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = utc_now()
    row = AuthSession(
        id_hash=sha256_hex(token),
        user_id=user.id,
        csrf_hash=sha256_hex(csrf_token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
        ip=ip,
    )
    session.add(row)
    await session.flush()
    return NewSession(token=token, csrf_token=csrf_token, row=row)


async def load_session(
    session: AsyncSession, token: str, settings: Settings, now: datetime
) -> tuple[AuthSession, User] | None:
    row = await session.get(AuthSession, sha256_hex(token))
    if row is None:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.disabled or is_expired(row, settings, now):
        await session.delete(row)
        return None
    if now - row.last_seen_at > TOUCH_AFTER:
        row.last_seen_at = now
    return row, user


async def delete_session(session: AsyncSession, token_hash: str) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.id_hash == token_hash))


async def delete_user_sessions(
    session: AsyncSession, user_id: uuid.UUID, keep_hash: str | None = None
) -> None:
    statement = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_hash is not None:
        statement = statement.where(AuthSession.id_hash != keep_hash)
    await session.execute(statement)
