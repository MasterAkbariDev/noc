import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit, verify_chain
from noc.db.models import AuditEntry, ManagedResourceRow, Target
from noc.db.session import SessionFactory, transaction
from noc.policy.models import AutomationLevel, Environment
from noc.store.targets import add_target, set_auto_actions, set_automation, set_profile
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

KNOWN_ACTIONS = frozenset({"restart_service", "clear_cache"})
RESOURCE_ID = "svc:demo-shop"
TARGET_NAME = "demo-1"


async def load_target(session: AsyncSession) -> Target:
    return (await session.scalars(select(Target))).one()


async def load_resource(session: AsyncSession) -> ManagedResourceRow:
    target = await load_target(session)
    row = await session.get(ManagedResourceRow, (target.id, RESOURCE_ID))
    assert row is not None
    return row


@pytest.fixture
async def target_name(sessions: SessionFactory) -> str:
    async with transaction(sessions) as session:
        target = await add_target(
            session, TARGET_NAME, "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        session.add(
            ManagedResourceRow(
                target_id=target.id,
                resource_id=RESOURCE_ID,
                kind="service",
                name="demo-shop",
                allowed_actions=["restart_service"],
            )
        )
    return TARGET_NAME


async def test_set_automation_persists_level(sessions: SessionFactory, target_name: str) -> None:
    async with transaction(sessions) as session:
        await set_automation(session, target_name, AutomationLevel.APPROVAL_REQUIRED)
    async with sessions() as session:
        assert (await load_target(session)).automation_level == "approval_required"


async def test_set_auto_actions_stores_known_actions(
    sessions: SessionFactory, target_name: str
) -> None:
    async with transaction(sessions) as session:
        await set_auto_actions(session, target_name, ["restart_service"], KNOWN_ACTIONS)
    async with sessions() as session:
        assert (await load_target(session)).auto_actions == ["restart_service"]


async def test_unknown_action_is_rejected_and_nothing_changes(
    sessions: SessionFactory, target_name: str
) -> None:
    with pytest.raises(ValueError, match="format_disk"):
        async with transaction(sessions) as session:
            await set_auto_actions(
                session, target_name, ["restart_service", "format_disk"], KNOWN_ACTIONS
            )
    async with sessions() as session:
        assert (await load_target(session)).auto_actions == []


async def test_unknown_target_is_rejected(sessions: SessionFactory, target_name: str) -> None:
    with pytest.raises(ValueError, match="unknown target"):
        async with transaction(sessions) as session:
            await set_automation(session, "missing", AutomationLevel.AUTO_SAFE)


async def test_set_profile_stores_validated_profile(
    sessions: SessionFactory, target_name: str
) -> None:
    profile_json = '{"serves_user_traffic": false, "enabled_actions": ["restart_service"]}'
    async with transaction(sessions) as session:
        await set_profile(session, target_name, RESOURCE_ID, profile_json)
    async with sessions() as session:
        assert (await load_resource(session)).profile == {
            "criticality": "normal",
            "redundancy": "none",
            "serves_user_traffic": False,
            "enabled_actions": ["restart_service"],
        }


async def test_invalid_profile_is_rejected(sessions: SessionFactory, target_name: str) -> None:
    with pytest.raises(ValidationError):
        async with transaction(sessions) as session:
            await set_profile(session, target_name, RESOURCE_ID, '{"criticality": "bogus"}')
    async with sessions() as session:
        assert (await load_resource(session)).profile is None


async def test_profile_for_unknown_resource_is_rejected(
    sessions: SessionFactory, target_name: str
) -> None:
    with pytest.raises(ValueError, match="unknown resource"):
        async with transaction(sessions) as session:
            await set_profile(session, target_name, "svc:missing", "{}")


async def test_admin_commands_keep_audit_chain_intact(
    sessions: SessionFactory, target_name: str
) -> None:
    async with transaction(sessions) as session:
        await set_automation(session, target_name, AutomationLevel.APPROVAL_REQUIRED)
        await append_audit(
            session, "cli", "target_automation_set", target_name, {"level": "approval_required"}
        )
    async with transaction(sessions) as session:
        await set_auto_actions(session, target_name, ["clear_cache"], KNOWN_ACTIONS)
        await append_audit(
            session, "cli", "target_auto_actions_set", target_name, {"actions": ["clear_cache"]}
        )
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEntry)) == 2
        assert await verify_chain(session) is None
