import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import Principal, get_session, require_role
from noc.audit.chain import append_audit
from noc.auth.roles import Role
from noc.db.base import utc_now
from noc.db.models import Endpoint
from noc.endpoints.service import clean_host, clean_url, run_check

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminPrincipal = Annotated[Principal, Depends(require_role(Role.ADMIN))]
ViewerPrincipal = Annotated[Principal, Depends(require_role(Role.VIEWER))]
NOT_FOUND = "server not found"


class AddEndpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    url: str | None = Field(default=None, max_length=512)


class EndpointView(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    ssh_port: int
    url: str | None
    last_checked_at: datetime | None
    last_result: dict[str, Any] | None


def endpoint_view(row: Endpoint) -> EndpointView:
    return EndpointView(
        id=row.id,
        name=row.name,
        host=row.host,
        ssh_port=row.ssh_port,
        url=row.url,
        last_checked_at=row.last_checked_at,
        last_result=row.last_result,
    )


async def load(session: AsyncSession, endpoint_id: uuid.UUID) -> Endpoint:
    row = await session.get(Endpoint, endpoint_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return row


@router.get("")
async def list_endpoints(viewer: ViewerPrincipal, session: Session) -> list[EndpointView]:
    rows = await session.scalars(select(Endpoint).order_by(Endpoint.name))
    return [endpoint_view(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_endpoint(
    body: AddEndpointRequest, admin: AdminPrincipal, session: Session
) -> EndpointView:
    try:
        host = clean_host(body.host)
        url = clean_url(body.url)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the name cannot be empty")
    if await session.scalar(select(Endpoint.id).where(Endpoint.name == name)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{name} already exists")
    row = Endpoint(name=name, host=host, ssh_port=body.ssh_port, url=url, created_by=admin.username)
    session.add(row)
    await session.flush()
    await append_audit(
        session, admin.username, "endpoint_added", f"endpoint:{name}", {"host": host, "url": url}
    )
    await session.commit()
    return endpoint_view(row)


@router.post("/{endpoint_id}/check")
async def check(endpoint_id: uuid.UUID, admin: AdminPrincipal, session: Session) -> EndpointView:
    row = await load(session, endpoint_id)
    row.last_result = await run_check(row.host, row.ssh_port, row.url)
    row.last_checked_at = utc_now()
    await session.commit()
    return endpoint_view(row)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_endpoint(endpoint_id: uuid.UUID, admin: AdminPrincipal, session: Session) -> None:
    row = await load(session, endpoint_id)
    await append_audit(session, admin.username, "endpoint_removed", f"endpoint:{row.name}", {})
    await session.delete(row)
    await session.commit()
