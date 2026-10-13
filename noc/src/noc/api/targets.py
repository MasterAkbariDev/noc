import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_token
from noc.api.schemas import TargetResourceView, TargetView
from noc.db.models import ManagedResourceRow, Target

router = APIRouter(prefix="/api/targets", tags=["targets"], dependencies=[Depends(require_token)])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_targets(session: Session) -> list[TargetView]:
    targets = list(await session.scalars(select(Target).order_by(Target.name)))
    resources = await session.scalars(
        select(ManagedResourceRow).order_by(ManagedResourceRow.resource_id)
    )
    resources_by_target: defaultdict[uuid.UUID, list[TargetResourceView]] = defaultdict(list)
    for resource in resources:
        resources_by_target[resource.target_id].append(TargetResourceView.model_validate(resource))
    return [target_view(target, resources_by_target[target.id]) for target in targets]


def target_view(target: Target, resources: list[TargetResourceView]) -> TargetView:
    return TargetView(
        id=target.id,
        name=target.name,
        environment=target.environment,
        automation_level=target.automation_level,
        halted=target.halted,
        last_inventory_at=target.last_inventory_at,
        resources=resources,
    )
