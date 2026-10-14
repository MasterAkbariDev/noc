from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import ManagedResourceRow, Target
from noc.domain.variants import Variant
from noc.policy.models import AutomationLevel, Environment, ServiceProfile
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


async def get_target(session: AsyncSession, name: str) -> Target:
    target = await find_target(session, name)
    if target is None:
        raise ValueError(f"unknown target {name}")
    return target


async def list_resources(session: AsyncSession, target: Target) -> list[ManagedResourceRow]:
    rows = await session.scalars(
        select(ManagedResourceRow)
        .where(ManagedResourceRow.target_id == target.id)
        .order_by(ManagedResourceRow.resource_id)
    )
    return list(rows)


async def set_automation(session: AsyncSession, name: str, level: AutomationLevel) -> Target:
    target = await get_target(session, name)
    target.automation_level = level.value
    await session.flush()
    return target


async def set_auto_actions(
    session: AsyncSession, name: str, actions: list[str], known_actions: frozenset[str]
) -> Target:
    unknown = sorted(set(actions) - known_actions)
    if unknown:
        raise ValueError(f"actions not in the policy catalog: {', '.join(unknown)}")
    target = await get_target(session, name)
    target.auto_actions = list(actions)
    await session.flush()
    return target


async def set_profile(
    session: AsyncSession, name: str, resource_id: str, profile_json: str
) -> ManagedResourceRow:
    profile = ServiceProfile.model_validate_json(profile_json)
    target = await get_target(session, name)
    row = await session.get(ManagedResourceRow, (target.id, resource_id))
    if row is None:
        raise ValueError(f"unknown resource {resource_id} on target {name}")
    row.profile = profile.model_dump(mode="json")
    await session.flush()
    return row


async def rotate_hmac_key(session: AsyncSession, name: str, new_key_id: str, actor: str) -> str:
    target = await get_target(session, name)
    previous = target.hmac_key_id
    if new_key_id == previous:
        raise ValueError(f"{name} already uses key {new_key_id}")
    target.hmac_key_id = new_key_id
    await session.flush()
    await append_audit(
        session,
        actor,
        "target_key_rotated",
        f"target:{name}",
        {"from": previous, "to": new_key_id},
    )
    return previous


async def set_variant_override(
    session: AsyncSession, name: str, variant: Variant | None, actor: str
) -> Target:
    target = await get_target(session, name)
    if variant is not None and target.environment != Environment.LAB.value:
        raise ValueError(f"{name} is not a lab target; a variant override is only for lab")
    previous = target.variant_override
    target.variant_override = variant
    await session.flush()
    action = "target_variant_cleared" if variant is None else "target_variant_set"
    await append_audit(
        session,
        actor,
        action,
        f"target:{name}",
        {"from": previous, "to": variant},
    )
    return target
