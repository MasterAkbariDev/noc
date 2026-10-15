import asyncio
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.auth.login_limits import clear_failures
from noc.auth.passwords import check_password_rules, hash_password, normalize_username
from noc.auth.roles import Role
from noc.auth.sessions import delete_user_sessions
from noc.auth.totp import new_secret
from noc.db.base import utc_now
from noc.db.models import User


class UserExists(ValueError):
    pass


class LastAdmin(ValueError):
    pass


LAST_ADMIN_MESSAGE = "this is the last active admin; make another admin first"


def subject_for(username: str) -> str:
    return f"user:{username}"


async def create_user(
    session: AsyncSession, username: str, password: str, role: Role, actor: str
) -> User:
    name = normalize_username(username)
    check_password_rules(password)
    password_hash = await asyncio.to_thread(hash_password, password)
    user = User(username=name, password_hash=password_hash, role=role.value)
    try:
        async with session.begin_nested():
            session.add(user)
            await session.flush()
    except IntegrityError as error:
        raise UserExists(f"user {name} already exists") from error
    await append_audit(session, actor, "user_created", subject_for(name), {"role": role.value})
    return user


async def find_user(session: AsyncSession, username: str) -> User | None:
    return await session.scalar(select(User).where(User.username == normalize_username(username)))


async def list_users(session: AsyncSession) -> list[User]:
    return list(await session.scalars(select(User).order_by(User.username)))


async def require_user(session: AsyncSession, username: str) -> User:
    user = await find_user(session, username)
    if user is None:
        raise LookupError(f"unknown user {username}")
    return user


async def lock_active_admins(session: AsyncSession) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(User.id)
        .where(User.role == Role.ADMIN.value, User.disabled.is_(False))
        .order_by(User.id)
        .with_for_update()
    )
    return list(rows)


async def ensure_not_last_admin(session: AsyncSession, user: User) -> None:
    active_admins = await lock_active_admins(session)
    if active_admins == [user.id]:
        raise LastAdmin(LAST_ADMIN_MESSAGE)


async def set_role(session: AsyncSession, username: str, role: Role, actor: str) -> User:
    user = await require_user(session, username)
    if role is not Role.ADMIN:
        await ensure_not_last_admin(session, user)
    previous = user.role
    user.role = role.value
    await session.flush()
    await append_audit(
        session,
        actor,
        "user_role_changed",
        subject_for(user.username),
        {"from": previous, "to": role.value},
    )
    return user


async def set_disabled(session: AsyncSession, username: str, disabled: bool, actor: str) -> User:
    user = await require_user(session, username)
    if disabled:
        await ensure_not_last_admin(session, user)
    user.disabled = disabled
    await session.flush()
    if disabled:
        await delete_user_sessions(session, user.id)
    action = "user_disabled" if disabled else "user_enabled"
    await append_audit(session, actor, action, subject_for(user.username), {})
    return user


async def reset_password(session: AsyncSession, username: str, password: str, actor: str) -> User:
    check_password_rules(password)
    user = await require_user(session, username)
    user.password_hash = await asyncio.to_thread(hash_password, password)
    user.password_changed_at = utc_now()
    await session.flush()
    await delete_user_sessions(session, user.id)
    await append_audit(session, actor, "user_password_reset", subject_for(user.username), {})
    return user


async def delete_user(session: AsyncSession, username: str, actor: str) -> str:
    user = await require_user(session, username)
    if user.role == Role.ADMIN.value and not user.disabled:
        await ensure_not_last_admin(session, user)
    name = user.username
    role = user.role
    await delete_user_sessions(session, user.id)
    await clear_failures(session, name)
    await session.delete(user)
    await session.flush()
    await append_audit(session, actor, "user_deleted", subject_for(name), {"role": role})
    return name


async def unlock_user(session: AsyncSession, username: str, actor: str) -> int:
    user = await require_user(session, username)
    cleared = await clear_failures(session, user.username)
    await append_audit(
        session, actor, "user_unlocked", subject_for(user.username), {"cleared": cleared}
    )
    return cleared


async def claim_totp_step(session: AsyncSession, user_id: uuid.UUID, step: int) -> bool:
    claimed = await session.scalar(
        update(User)
        .where(User.id == user_id, (User.totp_last_step.is_(None)) | (User.totp_last_step < step))
        .values(totp_last_step=step)
        .returning(User.id)
    )
    return claimed is not None


async def begin_totp_setup(session: AsyncSession, user: User) -> str:
    user.totp_secret = new_secret()
    user.totp_enabled = False
    user.totp_last_step = None
    await session.flush()
    return user.totp_secret


async def enable_totp(session: AsyncSession, user: User, step: int, actor: str) -> None:
    user.totp_enabled = True
    user.totp_last_step = step
    await session.flush()
    await append_audit(session, actor, "totp_enabled", subject_for(user.username), {})


async def clear_totp(session: AsyncSession, user: User, actor: str) -> None:
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_step = None
    await session.flush()
    await delete_user_sessions(session, user.id)
    await append_audit(session, actor, "totp_cleared", subject_for(user.username), {})


async def enroll_totp(session: AsyncSession, username: str, actor: str) -> tuple[User, str]:
    user = await require_user(session, username)
    secret = await begin_totp_setup(session, user)
    user.totp_enabled = True
    await session.flush()
    await delete_user_sessions(session, user.id)
    await append_audit(session, actor, "totp_enrolled", subject_for(user.username), {})
    return user, secret
