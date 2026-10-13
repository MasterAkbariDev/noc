from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from noc.api.app import create_app
from noc.config import Settings
from noc.db.models import ManagedResourceRow
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
HIDDEN_FIELDS = ("sentinel_url", "address", "hmac_key_id")


@pytest.fixture
async def targets(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        zeta = await add_target(
            session, "zeta-2", "10.0.0.9", "https://zeta-2:9443", Environment.LAB, KEY_ID
        )
        alpha = await add_target(
            session, "alpha-1", "10.0.0.2", "https://alpha-1:9443", Environment.LAB, KEY_ID
        )
        alpha.halted = True
        session.add(
            ManagedResourceRow(
                target_id=alpha.id,
                resource_id="svc:web",
                kind="service",
                name="web",
                allowed_actions=["restart_service"],
            )
        )
        session.add(
            ManagedResourceRow(
                target_id=alpha.id,
                resource_id="svc:cache",
                kind="service",
                name="cache",
                allowed_actions=["clear_cache"],
            )
        )
        session.add(
            ManagedResourceRow(
                target_id=zeta.id,
                resource_id="svc:db",
                kind="service",
                name="db",
                allowed_actions=[],
            )
        )


@pytest.fixture
async def client(sessions: SessionFactory) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(TOKEN))
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def test_targets_require_token(client: httpx.AsyncClient, targets: None) -> None:
    response = await client.get("/api/targets")
    assert response.status_code == 401


async def test_targets_are_listed_by_name_with_resources(
    client: httpx.AsyncClient, targets: None
) -> None:
    response = await client.get("/api/targets", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert [target["name"] for target in body] == ["alpha-1", "zeta-2"]
    alpha, zeta = body
    assert [resource["resource_id"] for resource in alpha["resources"]] == [
        "svc:cache",
        "svc:web",
    ]
    assert zeta["resources"] == [{"resource_id": "svc:db", "kind": "service", "name": "db"}]


async def test_targets_hide_addresses_and_keys(client: httpx.AsyncClient, targets: None) -> None:
    response = await client.get("/api/targets", headers=AUTH)
    for target in response.json():
        for field in HIDDEN_FIELDS:
            assert field not in target


async def test_targets_show_halted_flag(client: httpx.AsyncClient, targets: None) -> None:
    response = await client.get("/api/targets", headers=AUTH)
    halted = {target["name"]: target["halted"] for target in response.json()}
    assert halted == {"alpha-1": True, "zeta-2": False}
