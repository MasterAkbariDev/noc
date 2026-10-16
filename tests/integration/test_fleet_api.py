import stat
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select, update

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.api.tickets import TicketStore
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.totp import counter_code, step_at
from noc.auth.users import create_user, enroll_totp
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuditEntry, SshKey, User
from noc.db.session import SessionFactory, transaction
from noc.fleet.keys import passphrase_secret_name, private_key_secret_name
from noc.policy.models import Environment
from noc.secret_store import SecretStore
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
PASSWORD = "correct horse battery"
NOC_IP = "198.51.100.4"


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        secrets_dir=tmp_path / "secrets",
        _env_file=None,
    )


def scrape(job: str, health: str) -> dict[str, Any]:
    return {"labels": {"target": "demo-1", "job": job}, "health": health, "lastError": ""}


def prometheus_answer(request: httpx.Request) -> httpx.Response:
    targets = [scrape("node", "up"), scrape("sentinel", "up")]
    return httpx.Response(
        200, json={"status": "success", "data": {"activeTargets": targets, "droppedTargets": []}}
    )


def make_app(settings: Settings, sessions: SessionFactory) -> FastAPI:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tickets = TicketStore()
    prometheus_http = httpx.AsyncClient(transport=httpx.MockTransport(prometheus_answer))
    app.state.prometheus = PrometheusReader(prometheus_http, settings.prometheus_url)
    return app


async def signed_in(
    settings: Settings, sessions: SessionFactory, role: Role, totp: bool
) -> tuple[httpx.AsyncClient, str | None]:
    app = make_app(settings, sessions)
    secret = None
    async with transaction(sessions) as session:
        await create_user(session, "ada", PASSWORD, role, "cli")
        if totp:
            _, secret = await enroll_totp(session, "ada", "cli")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://noc")
    body: dict[str, str] = {"username": "ada", "password": PASSWORD}
    if secret is not None:
        body["totp"] = counter_code(secret, step_at(utc_now()) - 1)
    assert (await http.post("/api/auth/login", json=body)).status_code == 200
    return http, secret


@pytest.fixture
async def admin(
    settings: Settings, sessions: SessionFactory
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    http, secret = await signed_in(settings, sessions, Role.ADMIN, totp=True)
    assert secret is not None
    yield http, secret
    await http.aclose()


async def fresh_code(sessions: SessionFactory, secret: str) -> str:
    async with transaction(sessions) as session:
        await session.execute(update(User).values(totp_last_step=None))
    return counter_code(secret, step_at(utc_now()))


async def post(
    admin: tuple[httpx.AsyncClient, str],
    sessions: SessionFactory,
    path: str,
    body: dict[str, Any] | None = None,
    with_code: bool = True,
) -> httpx.Response:
    http, secret = admin
    payload = dict(body or {})
    if with_code:
        payload["totp"] = await fresh_code(sessions, secret)
    return await http.post(
        path, json=payload, headers={CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}
    )


async def add_host(admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory) -> str:
    response = await post(
        admin,
        sessions,
        "/api/fleet/hosts",
        {"name": "demo-2", "address": "203.0.113.7", "environment": "lab"},
    )
    assert response.status_code == 204
    fleet = (await admin[0].get("/api/fleet")).json()
    host_id: str = next(row["host_id"] for row in fleet["hosts"] if row["name"] == "demo-2")
    return host_id


async def add_key(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory, **changes: Any
) -> dict[str, Any]:
    body = {
        "label": "lab ops",
        "purpose": "ops",
        "environment": "lab",
        "from_pin": NOC_IP,
        "with_passphrase": True,
        **changes,
    }
    response = await post(admin, sessions, "/api/fleet/keys", body)
    assert response.status_code == 200, response.text
    key: dict[str, Any] = response.json()
    return key


async def audit_actions(sessions: SessionFactory) -> list[str]:
    async with sessions() as session:
        return list(await session.scalars(select(AuditEntry.action).order_by(AuditEntry.id)))


async def test_generating_a_key_keeps_private_parts_in_the_secret_store_only(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory, settings: Settings
) -> None:
    key = await add_key(admin, sessions)

    store = SecretStore(settings.secrets_dir)
    key_id = uuid.UUID(key["id"])
    private = store.read(private_key_secret_name(key_id))
    passphrase = store.read(passphrase_secret_name(key_id))
    assert private is not None
    assert private.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert passphrase is not None
    path = store.path_for(private_key_secret_name(key_id))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    listing = (await admin[0].get("/api/fleet")).text
    for text in (listing, str(key)):
        assert "PRIVATE KEY" not in text
        assert passphrase not in text
    assert key["state"] == "active"
    assert key["rotation_days"] == 90
    assert key["has_passphrase"] is True
    assert "ssh_key_generated" in await audit_actions(sessions)


async def test_every_change_needs_a_fresh_code(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory
) -> None:
    response = await post(
        admin,
        sessions,
        "/api/fleet/keys",
        {"label": "x", "purpose": "bootstrap", "environment": "lab"},
        with_code=False,
    )
    assert response.status_code == 403
    async with sessions() as session:
        assert (await session.scalars(select(SshKey))).first() is None


async def test_an_admin_without_two_factor_cannot_change_keys(
    settings: Settings, sessions: SessionFactory
) -> None:
    http, _ = await signed_in(settings, sessions, Role.ADMIN, totp=False)
    response = await http.post(
        "/api/fleet/keys",
        json={"label": "x", "purpose": "bootstrap", "environment": "lab"},
        headers={CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""},
    )
    await http.aclose()
    assert response.status_code == 403
    assert "two-factor" in response.json()["detail"]


async def test_operators_cannot_see_the_fleet(settings: Settings, sessions: SessionFactory) -> None:
    http, _ = await signed_in(settings, sessions, Role.OPERATOR, totp=False)
    assert (await http.get("/api/fleet")).status_code == 403
    await http.aclose()


async def test_api_token_cannot_change_keys(settings: Settings, sessions: SessionFactory) -> None:
    app = make_app(settings, sessions)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        response = await http.post(
            "/api/fleet/keys",
            json={"label": "x", "purpose": "bootstrap", "environment": "lab", "totp": "123456"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 403
    assert "signed-in person" in response.json()["detail"]


async def test_ops_key_without_pin_is_refused(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory
) -> None:
    response = await post(
        admin,
        sessions,
        "/api/fleet/keys",
        {"label": "ops", "purpose": "ops", "environment": "lab"},
    )
    assert response.status_code == 422
    assert "pinned" in response.json()["detail"]


async def test_fleet_lists_targets_and_hosts_together(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory
) -> None:
    async with transaction(sessions) as session:
        target = await add_target(
            session, "demo-1", "10.0.0.2", "https://10.0.0.2:9444", Environment.LAB, KEY_ID
        )
        target.sentinel_version = "0.2.0"
    await add_host(admin, sessions)

    fleet = (await admin[0].get("/api/fleet")).json()

    rows = {row["name"]: row for row in fleet["hosts"]}
    assert rows["demo-1"]["host_id"] is None
    assert rows["demo-1"]["helper_version"] == "0.2.0"
    assert rows["demo-1"]["automation_level"] == "auto_safe"
    assert rows["demo-1"]["reachable"] is True
    assert rows["demo-1"]["helper_up"] is True
    assert rows["demo-1"]["notes"]
    assert rows["demo-2"]["ssh_user"] == "ops"
    assert rows["demo-2"]["ssh_port"] == 22
    assert rows["demo-2"]["target_id"] is None
    assert rows["demo-2"]["reachable"] is None
    assert fleet["metrics_available"] is True
    assert {rule["purpose"] for rule in fleet["rules"]} == {"bootstrap", "ops", "operator-shell"}


async def test_paste_command_install_and_revoke(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory, settings: Settings
) -> None:
    host_id = await add_host(admin, sessions)
    key = await add_key(admin, sessions)

    paste = await post(
        admin,
        sessions,
        f"/api/fleet/hosts/{host_id}/paste-command",
        {"key_id": key["id"]},
        with_code=False,
    )
    assert paste.status_code == 200
    steps = paste.json()["steps"]
    assert f'from="{NOC_IP}"' in steps[0]["command"]
    assert key["public_key"] in steps[0]["command"]
    assert "PRIVATE" not in paste.text

    marked = await post(
        admin,
        sessions,
        f"/api/fleet/hosts/{host_id}/installed",
        {"key_id": key["id"], "sudo_scope_ok": True},
    )
    assert marked.status_code == 204
    row = next(
        row for row in (await admin[0].get("/api/fleet")).json()["hosts"] if row["name"] == "demo-2"
    )
    assert [installed["key_id"] for installed in row["keys"]] == [key["id"]]
    assert row["notes"] == []

    revoked = await post(admin, sessions, f"/api/fleet/keys/{key['id']}/revoke")
    assert revoked.status_code == 200
    assert f"noc-key-{key['id']}" in revoked.json()["steps"][0]["command"]
    store = SecretStore(settings.secrets_dir)
    assert store.read(private_key_secret_name(uuid.UUID(key["id"]))) is None
    assert store.read(passphrase_secret_name(uuid.UUID(key["id"]))) is None
    fleet = (await admin[0].get("/api/fleet")).json()
    assert next(item for item in fleet["keys"] if item["id"] == key["id"])["state"] == "retired"
    actions = await audit_actions(sessions)
    assert {"fleet_host_added", "ssh_key_installed", "ssh_key_revoked"} <= set(actions)


async def test_prod_key_cannot_go_on_a_lab_server(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory
) -> None:
    host_id = await add_host(admin, sessions)
    key = await add_key(admin, sessions, environment="prod", label="prod ops")

    paste = await post(
        admin,
        sessions,
        f"/api/fleet/hosts/{host_id}/paste-command",
        {"key_id": key["id"]},
        with_code=False,
    )

    assert paste.status_code == 422
    assert "kept apart" in paste.json()["detail"]


async def test_rotation_swaps_the_key_on_every_host(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory, settings: Settings
) -> None:
    host_id = await add_host(admin, sessions)
    old = await add_key(admin, sessions)
    await post(
        admin,
        sessions,
        f"/api/fleet/hosts/{host_id}/installed",
        {"key_id": old["id"], "sudo_scope_ok": True},
    )

    started = await post(admin, sessions, f"/api/fleet/keys/{old['id']}/rotate")
    assert started.status_code == 200
    new = started.json()["new_key"]
    assert new["replaces_id"] == old["id"]
    command = started.json()["steps"][0]["command"]
    assert new["public_key"] in command
    assert f"/ noc-key-{old['id']}$/d" in command
    again = await post(admin, sessions, f"/api/fleet/keys/{old['id']}/rotate")
    assert again.status_code == 422
    listing = (await admin[0].get("/api/fleet")).json()
    assert next(item for item in listing["keys"] if item["id"] == old["id"])["state"] == "rotating"

    finished = await post(admin, sessions, f"/api/fleet/keys/{new['id']}/finish-rotation")
    assert finished.status_code == 200
    assert finished.json()["hosts"] == ["demo-2"]
    store = SecretStore(settings.secrets_dir)
    assert store.read(private_key_secret_name(uuid.UUID(old["id"]))) is None
    assert store.read(private_key_secret_name(uuid.UUID(new["id"]))) is not None
    assert "ssh_key_rotated" in await audit_actions(sessions)


async def test_offboarding_removes_the_host_and_lists_cleanup_commands(
    admin: tuple[httpx.AsyncClient, str], sessions: SessionFactory
) -> None:
    host_id = await add_host(admin, sessions)
    key = await add_key(admin, sessions)
    await post(
        admin,
        sessions,
        f"/api/fleet/hosts/{host_id}/installed",
        {"key_id": key["id"], "sudo_scope_ok": False},
    )

    response = await post(admin, sessions, f"/api/fleet/hosts/{host_id}/offboard")

    assert response.status_code == 200
    commands = " ".join(step["command"] for step in response.json()["steps"])
    assert "--uninstall" in commands
    assert f"noc-key-{key['id']}" in commands
    fleet = (await admin[0].get("/api/fleet")).json()
    assert [row["name"] for row in fleet["hosts"]] == []
    assert "fleet_host_offboarded" in await audit_actions(sessions)
