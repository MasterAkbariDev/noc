import asyncio
from typing import Any

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from noc.audit.chain import verify_chain
from noc.auth.passwords import verify_password
from noc.auth.roles import Role
from noc.auth.users import (
    UserExists,
    create_user,
    find_user,
    list_users,
    reset_password,
    set_disabled,
    set_role,
)
from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.models import AuditEntry, User
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery"
NEW_PASSWORD = "another long password"


@pytest.fixture
def cli_settings(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: Settings(database_url=database_url))


async def load_user(sessions: SessionFactory, username: str) -> User:
    async with sessions() as session:
        user = await find_user(session, username)
    assert user is not None
    return user


async def audit_rows(sessions: SessionFactory) -> list[tuple[str, str, dict[str, Any]]]:
    async with sessions() as session:
        result = await session.execute(
            select(AuditEntry.action, AuditEntry.subject, AuditEntry.payload).order_by(
                AuditEntry.id
            )
        )
        return [(row.action, row.subject, row.payload) for row in result]


async def test_created_user_is_found_listed_and_stores_argon2_hash(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "Bob.Ops", PASSWORD, Role.OPERATOR, "cli")
        await create_user(session, "alice", PASSWORD, Role.VIEWER, "cli")
    bob = await load_user(sessions, "bob.ops")
    assert bob.role == "operator"
    assert bob.disabled is False
    assert bob.password_hash != PASSWORD
    assert verify_password(bob.password_hash, PASSWORD) is True
    async with sessions() as session:
        assert [user.username for user in await list_users(session)] == ["alice", "bob.ops"]
        assert await find_user(session, "missing") is None


async def test_duplicate_username_is_rejected_and_first_user_is_kept(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.VIEWER, "cli")
    with pytest.raises(UserExists):
        async with transaction(sessions) as session:
            await create_user(session, "ALICE", NEW_PASSWORD, Role.ADMIN, "cli")
    alice = await load_user(sessions, "alice")
    assert alice.role == "viewer"
    assert verify_password(alice.password_hash, PASSWORD) is True


async def test_weak_password_is_rejected_and_nothing_is_stored(sessions: SessionFactory) -> None:
    with pytest.raises(ValueError, match="12-128 characters"):
        async with transaction(sessions) as session:
            await create_user(session, "alice", "short", Role.VIEWER, "cli")
    async with sessions() as session:
        assert await list_users(session) == []


async def test_admin_changes_write_audit_entries_and_keep_chain_intact(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.VIEWER, "cli")
    async with transaction(sessions) as session:
        await set_role(session, "alice", Role.OPERATOR, "cli")
    async with transaction(sessions) as session:
        await set_disabled(session, "alice", True, "cli")
    async with transaction(sessions) as session:
        await reset_password(session, "alice", NEW_PASSWORD, "cli")
    assert await audit_rows(sessions) == [
        ("user_created", "user:alice", {"role": "viewer"}),
        ("user_role_changed", "user:alice", {"from": "viewer", "to": "operator"}),
        ("user_disabled", "user:alice", {}),
        ("user_password_reset", "user:alice", {}),
    ]
    async with sessions() as session:
        assert await verify_chain(session) is None
    alice = await load_user(sessions, "alice")
    assert alice.role == "operator"
    assert alice.disabled is True
    assert verify_password(alice.password_hash, NEW_PASSWORD) is True


async def test_audit_never_holds_a_password_or_hash(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.VIEWER, "cli")
    async with transaction(sessions) as session:
        await reset_password(session, "alice", NEW_PASSWORD, "cli")
    alice = await load_user(sessions, "alice")
    recorded = repr(await audit_rows(sessions))
    for secret in (PASSWORD, NEW_PASSWORD, alice.password_hash):
        assert secret not in recorded


async def test_admin_change_for_unknown_user_is_rejected(sessions: SessionFactory) -> None:
    with pytest.raises(LookupError, match="unknown user ghost"):
        async with transaction(sessions) as session:
            await set_disabled(session, "ghost", True, "cli")
    assert await audit_rows(sessions) == []


async def test_cli_create_reads_password_from_stdin(
    sessions: SessionFactory, cli_settings: None
) -> None:
    runner = CliRunner()
    result = await asyncio.to_thread(
        runner.invoke,
        cli_app,
        ["users", "create", "alice", "--role", "viewer", "--password-stdin"],
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "alice: role=viewer disabled=False" in result.output
    assert PASSWORD not in result.output
    alice = await load_user(sessions, "alice")
    assert verify_password(alice.password_hash, PASSWORD) is True


async def test_cli_create_prompts_for_password_with_confirmation(
    sessions: SessionFactory, cli_settings: None
) -> None:
    runner = CliRunner()
    result = await asyncio.to_thread(
        runner.invoke,
        cli_app,
        ["users", "create", "alice", "--role", "admin"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    alice = await load_user(sessions, "alice")
    assert alice.role == "admin"
    assert verify_password(alice.password_hash, PASSWORD) is True


async def test_cli_create_with_mismatched_confirmation_fails(
    sessions: SessionFactory, cli_settings: None
) -> None:
    runner = CliRunner()
    result = await asyncio.to_thread(
        runner.invoke,
        cli_app,
        ["users", "create", "alice", "--role", "admin"],
        input=f"{PASSWORD}\n{NEW_PASSWORD}\n",
    )
    assert result.exit_code != 0
    async with sessions() as session:
        assert await list_users(session) == []


async def test_cli_disable_unknown_user_is_a_usage_error(
    sessions: SessionFactory, cli_settings: None
) -> None:
    runner = CliRunner()
    result = await asyncio.to_thread(runner.invoke, cli_app, ["users", "disable", "ghost"])
    assert result.exit_code == 2
    assert "unknown user ghost" in result.output


async def test_cli_list_prints_header_and_users(
    sessions: SessionFactory, cli_settings: None
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.VIEWER, "cli")
    runner = CliRunner()
    result = await asyncio.to_thread(runner.invoke, cli_app, ["users", "list"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].split() == ["username", "role", "disabled", "2fa", "last_login"]
    assert lines[1].split() == ["alice", "viewer", "no", "no", "-"]


async def test_cli_totp_enroll_turns_it_on_and_prints_the_secret(
    sessions: SessionFactory, cli_settings: None
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.OPERATOR, "cli")
    runner = CliRunner()
    result = await asyncio.to_thread(runner.invoke, cli_app, ["users", "totp-enroll", "alice"])
    assert result.exit_code == 0, result.output
    user = await load_user(sessions, "alice")
    assert user.totp_enabled is True
    assert user.totp_secret is not None
    assert f"secret {user.totp_secret}" in result.output
    assert "otpauth://totp/" in result.output
    actions = [row[0] for row in await audit_rows(sessions)]
    assert "totp_enrolled" in actions


async def test_cli_totp_reset_clears_it_and_ends_sessions(
    sessions: SessionFactory, cli_settings: None
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", PASSWORD, Role.OPERATOR, "cli")
    runner = CliRunner()
    await asyncio.to_thread(runner.invoke, cli_app, ["users", "totp-enroll", "alice"])
    result = await asyncio.to_thread(runner.invoke, cli_app, ["users", "totp-reset", "alice"])
    assert result.exit_code == 0, result.output
    user = await load_user(sessions, "alice")
    assert user.totp_enabled is False
    assert user.totp_secret is None
    assert user.totp_last_step is None


async def test_cli_totp_enroll_unknown_user_is_a_usage_error(
    sessions: SessionFactory, cli_settings: None
) -> None:
    runner = CliRunner()
    result = await asyncio.to_thread(runner.invoke, cli_app, ["users", "totp-enroll", "ghost"])
    assert result.exit_code == 2
    assert "unknown user ghost" in result.output
