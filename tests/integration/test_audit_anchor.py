import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from noc.audit.anchor import (
    AnchorError,
    anchor_filename,
    check_anchor,
    check_anchors,
    create_anchor,
    load_anchors,
    parse_anchor,
    read_key,
)
from noc.audit.chain import GENESIS_HASH, append_audit
from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

KEY = b"anchor-key-0123456789"
OTHER_KEY = b"another-key-0123456789"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


async def add_entries(sessions: SessionFactory, count: int) -> None:
    async with transaction(sessions) as session:
        for number in range(count):
            await append_audit(session, "tester", "something", f"subject:{number}", {})


async def test_anchor_records_the_last_entry_and_its_hash(sessions: SessionFactory) -> None:
    await add_entries(sessions, 3)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
        assert anchor.body.last_entry_id > 0
        assert await check_anchor(session, KEY, anchor) is None


async def test_an_empty_log_anchors_the_genesis_hash(sessions: SessionFactory) -> None:
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
        assert anchor.body.last_entry_id == 0
        assert anchor.body.head_hash == GENESIS_HASH
        assert await check_anchor(session, KEY, anchor) is None


async def test_later_entries_do_not_invalidate_an_older_anchor(sessions: SessionFactory) -> None:
    await add_entries(sessions, 2)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
    await add_entries(sessions, 2)
    async with sessions() as session:
        assert await check_anchor(session, KEY, anchor) is None


async def test_a_rewritten_entry_is_caught_by_the_anchor_even_if_the_chain_is_rebuilt(
    sessions: SessionFactory,
) -> None:
    await add_entries(sessions, 3)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
    async with transaction(sessions) as session:
        await session.execute(
            text("UPDATE audit_log SET hash = repeat('a', 64) WHERE id = :id"),
            {"id": anchor.body.last_entry_id},
        )
    async with sessions() as session:
        problem = await check_anchor(session, KEY, anchor)
    assert problem is not None
    assert "rewritten" in problem


async def test_a_truncated_log_is_caught(sessions: SessionFactory) -> None:
    await add_entries(sessions, 3)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
    async with transaction(sessions) as session:
        await session.execute(
            text("DELETE FROM audit_log WHERE id = :id"), {"id": anchor.body.last_entry_id}
        )
    async with sessions() as session:
        problem = await check_anchor(session, KEY, anchor)
    assert problem is not None
    assert "truncated" in problem


async def test_a_wrong_key_or_edited_file_fails_the_signature(sessions: SessionFactory) -> None:
    await add_entries(sessions, 2)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
        assert "signature" in str(await check_anchor(session, OTHER_KEY, anchor))
        forged = anchor.model_copy(
            update={"body": anchor.body.model_copy(update={"last_entry_id": 1})}
        )
        assert "signature" in str(await check_anchor(session, KEY, forged))


async def test_a_broken_chain_is_not_anchored(sessions: SessionFactory) -> None:
    await add_entries(sessions, 3)
    async with transaction(sessions) as session:
        await session.execute(
            text(
                "UPDATE audit_log SET actor = 'mallory' WHERE id = (SELECT min(id) FROM audit_log)"
            )
        )
    async with sessions() as session:
        with pytest.raises(AnchorError, match="broken"):
            await create_anchor(session, KEY, NOW)


async def test_files_round_trip_and_bad_files_are_reported(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    await add_entries(sessions, 2)
    async with sessions() as session:
        anchor = await create_anchor(session, KEY, NOW)
        (tmp_path / anchor_filename(anchor.body)).write_text(anchor.model_dump_json())
        (tmp_path / "anchor-broken.json").write_text("{not json")
        (tmp_path / "notes.txt").write_text("ignored")
        checks = await check_anchors(session, KEY, load_anchors(tmp_path))
    by_name = {check.name: check.problem for check in checks}
    assert by_name[anchor_filename(anchor.body)] is None
    assert by_name["anchor-broken.json"] == "not a valid anchor file"
    assert "notes.txt" not in by_name


def test_parse_refuses_extra_fields() -> None:
    with pytest.raises(AnchorError):
        parse_anchor('{"body": {}, "mac": "x", "extra": 1}')


def test_short_or_missing_keys_are_refused(tmp_path: Path) -> None:
    short = tmp_path / "short.key"
    short.write_bytes(b"abc")
    with pytest.raises(AnchorError, match="shorter"):
        read_key(short)
    with pytest.raises(AnchorError, match="cannot read"):
        read_key(tmp_path / "missing.key")
    good = tmp_path / "good.key"
    good.write_bytes(KEY + b"\n")
    assert read_key(good) == KEY


@pytest.fixture
def key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, database_url: str) -> Path:
    path = tmp_path / "audit-anchor.key"
    path.write_bytes(KEY)
    settings = Settings(database_url=database_url, audit_anchor_key_file=path, _env_file=None)
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings)
    return path


async def test_cli_writes_an_anchor_and_verify_checks_it(
    sessions: SessionFactory, key_file: Path, tmp_path: Path
) -> None:
    await add_entries(sessions, 2)
    anchors = tmp_path / "anchors"
    runner = CliRunner()
    written = await asyncio.to_thread(
        runner.invoke, cli_app, ["audit", "anchor", "--out", str(anchors)]
    )
    assert written.exit_code == 0, written.output
    assert len(list(anchors.glob("anchor-*.json"))) == 1
    checked = await asyncio.to_thread(
        runner.invoke, cli_app, ["audit", "verify", "--anchors", str(anchors)]
    )
    assert checked.exit_code == 0, checked.output
    assert "matches its anchors" in checked.output


async def test_cli_verify_fails_when_the_log_was_cut_after_anchoring(
    sessions: SessionFactory, key_file: Path, tmp_path: Path
) -> None:
    await add_entries(sessions, 3)
    runner = CliRunner()
    await asyncio.to_thread(runner.invoke, cli_app, ["audit", "anchor", "--out", str(tmp_path)])
    async with transaction(sessions) as session:
        await session.execute(
            text("DELETE FROM audit_log WHERE id = (SELECT max(id) FROM audit_log)")
        )
    result = await asyncio.to_thread(
        runner.invoke, cli_app, ["audit", "verify", "--anchors", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "truncated" in result.output


async def test_cli_anchor_without_a_key_is_a_usage_error(
    sessions: SessionFactory,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    settings = Settings(
        database_url=database_url,
        audit_anchor_key_file=key_file.with_name("missing.key"),
        _env_file=None,
    )
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings)
    result = await asyncio.to_thread(CliRunner().invoke, cli_app, ["audit", "anchor"])
    assert result.exit_code == 2
    assert "cannot read the anchor key" in result.output
