import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, require_role
from noc.api.schemas import CreateUserRequest, SetRoleRequest, SetUserPasswordRequest, UserView
from noc.auth.roles import Role, role_allows
from noc.auth.users import (
    LastAdmin,
    UserExists,
    create_user,
    delete_user,
    list_users,
    reset_password,
    set_disabled,
    set_role,
)
from noc.db.models import User

router = APIRouter(prefix="/api/users", tags=["users"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]

NOT_FOUND = "user not found"
SELF_DISABLE = "an admin cannot disable their own account"
SELF_DEMOTE = "an admin cannot lower their own role"
SELF_RESET = "use Settings > Change password for your own account"
SELF_DELETE = "an admin cannot remove their own account"


async def load_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return user


def is_caller(admin: Principal, user: User) -> bool:
    return admin.user_id is not None and admin.user_id == user.id


@router.get("")
async def get_users(admin: AdminPrincipal, session: Session) -> list[UserView]:
    return [UserView.model_validate(user) for user in await list_users(session)]


@router.post("")
async def add_user(body: CreateUserRequest, admin: AdminPrincipal, session: Session) -> UserView:
    try:
        user = await create_user(session, body.username, body.password, body.role, admin.username)
    except UserExists as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    try:
        await session.commit()
    except IntegrityError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"user {body.username} already exists"
        ) from error
    return UserView.model_validate(user)


@router.post("/{user_id}/role")
async def change_role(
    user_id: uuid.UUID, body: SetRoleRequest, admin: AdminPrincipal, session: Session
) -> UserView:
    user = await load_user(session, user_id)
    if is_caller(admin, user) and not role_allows(body.role, Role.ADMIN):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_DEMOTE)
    try:
        changed = await set_role(session, user.username, body.role, admin.username)
    except LastAdmin as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    return UserView.model_validate(changed)


@router.post("/{user_id}/disable")
async def disable_user(user_id: uuid.UUID, admin: AdminPrincipal, session: Session) -> UserView:
    user = await load_user(session, user_id)
    if is_caller(admin, user):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_DISABLE)
    try:
        changed = await set_disabled(session, user.username, True, admin.username)
    except LastAdmin as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    return UserView.model_validate(changed)


@router.post("/{user_id}/enable")
async def enable_user(user_id: uuid.UUID, admin: AdminPrincipal, session: Session) -> UserView:
    user = await load_user(session, user_id)
    changed = await set_disabled(session, user.username, False, admin.username)
    await session.commit()
    return UserView.model_validate(changed)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_password(
    user_id: uuid.UUID,
    body: SetUserPasswordRequest,
    admin: AdminPrincipal,
    session: Session,
) -> None:
    user = await load_user(session, user_id)
    if is_caller(admin, user):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_RESET)
    try:
        await reset_password(session, user.username, body.new_password, admin.username)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    await session.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(user_id: uuid.UUID, admin: AdminPrincipal, session: Session) -> None:
    user = await load_user(session, user_id)
    if is_caller(admin, user):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_DELETE)
    try:
        await delete_user(session, user.username, admin.username)
    except LastAdmin as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
