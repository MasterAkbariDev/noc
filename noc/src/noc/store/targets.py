from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import ManagedResourceRow, Target
from noc.policy.models import AutomationLevel, Environment
from noc_shared.resources import Inventory


async def add_target(
    session: AsyncSession,
    name: str,
    address: str,
    sentinel_url: str,
    environment: Environment,
    hmac_key_id: str,
    automation_level: AutomationLevel | None = None,
    llm_data_policy: str | None = None,
) -> Target:
    is_lab = environment is Environment.LAB
    target = Target(
        name=name,
        address=address,
        sentinel_url=sentinel_url,
        environment=environment.value,
        hmac_key_id=hmac_key_id,
        automation_level=(
            automation_level
            or (AutomationLevel.AUTO_SAFE if is_lab else AutomationLevel.OBSERVE_ONLY)
        ).value,
        llm_data_policy=llm_data_policy or ("full" if is_lab else "redacted"),
        auto_actions=[],
    )
    session.add(target)
    await session.flush()
    return target


async def apply_inventory(session: AsyncSession, target: Target, inventory: Inventory) -> int:
    existing = {
        row.resource_id: row
        for row in await session.scalars(
            select(ManagedResourceRow).where(ManagedResourceRow.target_id == target.id)
        )
    }
    reported = {resource.id for resource in inventory.resources}
    stale = [resource_id for resource_id in existing if resource_id not in reported]
    if stale:
        await session.execute(
            delete(ManagedResourceRow).where(
                ManagedResourceRow.target_id == target.id,
                ManagedResourceRow.resource_id.in_(stale),
            )
        )
    for resource in inventory.resources:
        row = existing.get(resource.id) or ManagedResourceRow(
            target_id=target.id, resource_id=resource.id
        )
        row.kind = resource.kind.value
        row.name = resource.name
        row.allowed_actions = list(resource.allowed_actions)
        session.add(row)
    target.halted = inventory.halted
    target.last_inventory_at = utc_now()
    await session.flush()
    return len(inventory.resources)


async def find_target(session: AsyncSession, name: str) -> Target | None:
    return await session.scalar(select(Target).where(Target.name == name))
