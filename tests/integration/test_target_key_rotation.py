import asyncio
import json
import os
import stat
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.models import AuditEntry, Target
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target

pytestmark = pytest.mark.integration

OLD_KEY = "demo-1-v1"
NEW_KEY = "demo-1-v2"
INVENTORY = {
    "target": "demo-1",
    "environment": "lab",
    "sentinel_version": "0.1.0",
    "halted": False,
    "resources": [],
}


@pytest.fixture
def key_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, database_url: str) -> Path:
    directory = tmp_path / "keys"
    directory.mkdir()
    settings = Settings(database_url=database_url, sentinel_key_dir=directory, _env_file=None)
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings)
    return directory


def sentinel_answers(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code == 200:
            return httpx.Response(200, content=json.dumps(INVENTORY))
        return httpx.Response(status_code, text="bad signature")

    def build(*_: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("noc.cli.main.build_sentinel_http", build)


async def add_demo_target(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.1", "https://10.0.0.1:9443", Environment.LAB, OLD_KEY
        )


async def run(*args: str) -> tuple[int, str]:
    result = await asyncio.to_thread(CliRunner().invoke, cli_app, ["targets", "rotate-key", *args])
    return result.exit_code, result.output


async def current_key(sessions: SessionFactory) -> str:
    async with sessions() as session:
        target = await session.scalar(select(Target).where(Target.name == "demo-1"))
    assert target is not None
    return target.hmac_key_id


async def test_generate_writes_an_owner_only_key_and_refuses_to_overwrite(
    sessions: SessionFactory, key_dir: Path
) -> None:
    await add_demo_target(sessions)
    code, output = await run("demo-1", "--new-key-id", NEW_KEY, "--generate")
    assert code == 0, output
    path = key_dir / f"{NEW_KEY}.key"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert len(path.read_text().strip()) == 64
    again, message = await run("demo-1", "--new-key-id", NEW_KEY, "--generate")
    assert again == 2
    assert "refusing to overwrite" in message
    assert await current_key(sessions) == OLD_KEY


async def test_activate_switches_the_key_after_a_live_check(
    sessions: SessionFactory, key_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_demo_target(sessions)
    (key_dir / f"{NEW_KEY}.key").write_text("f" * 64)
    sentinel_answers(monkeypatch, 200)
    code, output = await run("demo-1", "--new-key-id", NEW_KEY, "--activate")
    assert code == 0, output
    assert await current_key(sessions) == NEW_KEY
    async with sessions() as session:
        rows = list(
            await session.scalars(
                select(AuditEntry.payload).where(AuditEntry.action == "target_key_rotated")
            )
        )
    assert rows == [{"from": OLD_KEY, "to": NEW_KEY}]


async def test_activate_keeps_the_old_key_when_the_sentinel_refuses(
    sessions: SessionFactory, key_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_demo_target(sessions)
    (key_dir / f"{NEW_KEY}.key").write_text("f" * 64)
    sentinel_answers(monkeypatch, 401)
    code, output = await run("demo-1", "--new-key-id", NEW_KEY, "--activate")
    assert code == 2
    assert "did not accept" in output
    assert await current_key(sessions) == OLD_KEY


async def test_activate_without_the_key_file_changes_nothing(
    sessions: SessionFactory, key_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_demo_target(sessions)
    sentinel_answers(monkeypatch, 200)
    code, _ = await run("demo-1", "--new-key-id", NEW_KEY, "--activate")
    assert code == 2
    assert await current_key(sessions) == OLD_KEY


async def test_one_mode_flag_is_required(sessions: SessionFactory, key_dir: Path) -> None:
    await add_demo_target(sessions)
    neither, _ = await run("demo-1", "--new-key-id", NEW_KEY)
    both, _ = await run("demo-1", "--new-key-id", NEW_KEY, "--generate", "--activate")
    assert neither == both == 2


async def test_odd_key_ids_are_refused(sessions: SessionFactory, key_dir: Path) -> None:
    await add_demo_target(sessions)
    code, output = await run("demo-1", "--new-key-id", "../etc/passwd", "--generate")
    assert code == 2
    assert "letters, digits" in output
