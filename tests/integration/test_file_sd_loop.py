import json
from pathlib import Path

import pytest

from noc.db.session import SessionFactory, transaction
from noc.detection.file_sd import refresh_file_sd
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration


def file_state(directory: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: (path.stat().st_ino, path.stat().st_mtime_ns)
        for path in sorted(directory.glob("*.json"))
    }


async def test_refresh_writes_labelled_files_and_skips_unchanged(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )

    written = await refresh_file_sd(sessions, tmp_path)

    assert sorted(path.name for path in written) == ["node.json", "sentinel.json"]
    labels = {"target": "demo-1", "env": "lab"}
    assert json.loads((tmp_path / "node.json").read_text()) == [
        {"targets": ["10.0.0.2:9100"], "labels": labels}
    ]
    assert json.loads((tmp_path / "sentinel.json").read_text()) == [
        {"targets": ["demo-1:9443"], "labels": labels}
    ]

    before = file_state(tmp_path)
    assert await refresh_file_sd(sessions, tmp_path) == []
    assert file_state(tmp_path) == before


async def test_new_target_rewrites_only_on_next_refresh(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
    await refresh_file_sd(sessions, tmp_path)
    before = file_state(tmp_path)

    async with transaction(sessions) as session:
        await add_target(
            session, "demo-2", "10.0.0.3", "https://demo-2:9443", Environment.LAB, KEY_ID
        )
    written = await refresh_file_sd(sessions, tmp_path)

    assert sorted(path.name for path in written) == ["node.json", "sentinel.json"]
    assert file_state(tmp_path) != before
    node = json.loads((tmp_path / "node.json").read_text())
    assert [group["labels"]["target"] for group in node] == ["demo-1", "demo-2"]


async def test_a_target_without_a_sentinel_is_not_scraped_for_one(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    async with transaction(sessions) as session:
        await add_target(session, "server-95", "10.0.0.9", "", Environment.LAB, KEY_ID)

    await refresh_file_sd(sessions, tmp_path)

    labels = {"target": "server-95", "env": "lab"}
    assert json.loads((tmp_path / "node.json").read_text()) == [
        {"targets": ["10.0.0.9:9100"], "labels": labels}
    ]
    assert json.loads((tmp_path / "sentinel.json").read_text()) == []
