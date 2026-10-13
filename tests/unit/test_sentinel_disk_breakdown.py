import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noc.tools.catalog import build_read_tools
from noc.tools.sentinel_client import SentinelDirectory
from noc_sentinel.app import create_app
from noc_sentinel.config import DEFAULT_DISK_BREAKDOWN_ROOTS, SentinelConfig
from noc_sentinel.nonce_store import NonceStore
from noc_sentinel.tools.disk_breakdown import (
    FilesystemDiskBreakdown,
    ListDirectory,
    read_directory,
)
from noc_shared.signing import sign_request
from noc_shared.tools import DirectorySizes
from tests.support.builders import KEY_ID, SECRET, FakeSystemctl, sentinel_config

BLOCK = 512


class RecordingDiskBreakdown:
    def __init__(self) -> None:
        self.calls: list[list[Path]] = []

    def directory_sizes(self, roots: list[Path]) -> DirectorySizes:
        self.calls.append(roots)
        return DirectorySizes(roots=[], complete=True, scanned_entries=0)


def make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def allocated(path: Path) -> int:
    return os.lstat(path).st_blocks * BLOCK


def denying(locked: Path) -> ListDirectory:
    def list_directory(path: str) -> list[os.DirEntry[str]]:
        if path == str(locked):
            raise PermissionError(path)
        return read_directory(path)

    return list_directory


def test_totals_and_order_follow_the_real_tree(tmp_path: Path) -> None:
    root = tmp_path / "root"
    make_file(root / "a" / "one.bin", 200_000)
    make_file(root / "a" / "two.bin", 200_000)
    make_file(root / "b" / "big.bin", 300_000)
    make_file(root / "small.txt", 10)

    sizes = FilesystemDiskBreakdown().directory_sizes([root])

    root_size = sizes.roots[0]
    everything = [root, *root.rglob("*")]
    assert root_size.total_bytes == sum(allocated(path) for path in everything)
    assert root_size.readable is True
    assert [child.path for child in root_size.largest_children] == [
        str(root / "a"),
        str(root / "b"),
        str(root / "small.txt"),
    ]
    assert root_size.largest_files[0].path == str(root / "b" / "big.bin")
    assert sizes.complete is True
    assert sizes.scanned_entries == len(list(root.rglob("*")))


def test_children_and_files_are_capped_at_eight_and_sorted(tmp_path: Path) -> None:
    root = tmp_path / "root"
    for index in range(10):
        make_file(root / f"file-{index}.bin", (index + 1) * 10_000)

    root_size = FilesystemDiskBreakdown().directory_sizes([root]).roots[0]

    assert len(root_size.largest_children) == 8
    assert len(root_size.largest_files) == 8
    sizes = [child.size_bytes for child in root_size.largest_files]
    assert sizes == sorted(sizes, reverse=True)
    assert root_size.largest_files[0].path == str(root / "file-9.bin")


def test_symlink_loop_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    make_file(root / "f.bin", 1_000)
    os.symlink(root, root / "loop", target_is_directory=True)

    sizes = FilesystemDiskBreakdown().directory_sizes([root])

    assert sizes.complete is True
    assert sizes.scanned_entries == 2
    assert all("loop/" not in child.path for child in sizes.roots[0].largest_files)


def test_unreadable_subdirectory_is_counted_and_marked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    locked = root / "locked"
    make_file(locked / "secret.bin", 50_000)
    make_file(root / "ok.bin", 1_000)

    sizes = FilesystemDiskBreakdown(list_directory=denying(locked)).directory_sizes([root])

    root_size = sizes.roots[0]
    assert root_size.readable is False
    assert root_size.total_bytes is not None
    assert sizes.complete is True
    assert str(locked) in [child.path for child in root_size.largest_children]
    assert all("secret.bin" not in file.path for file in root_size.largest_files)


def test_unreadable_root_has_no_total(tmp_path: Path) -> None:
    root = tmp_path / "root"
    make_file(root / "f.bin", 1_000)

    sizes = FilesystemDiskBreakdown(list_directory=denying(root)).directory_sizes([root])

    root_size = sizes.roots[0]
    assert root_size.total_bytes is None
    assert root_size.readable is False
    assert root_size.largest_children == []
    assert root_size.largest_files == []


def test_entry_budget_stops_the_scan_and_marks_it_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "root"
    for index in range(10):
        make_file(root / f"file-{index}.bin", 100)

    sizes = FilesystemDiskBreakdown(max_entries=3).directory_sizes([root])

    assert sizes.complete is False
    assert sizes.scanned_entries == 3


def test_missing_and_symlinked_roots_are_skipped(tmp_path: Path) -> None:
    real = tmp_path / "real"
    make_file(real / "f.bin", 100)
    link = tmp_path / "link"
    os.symlink(real, link, target_is_directory=True)

    sizes = FilesystemDiskBreakdown().directory_sizes([tmp_path / "missing", link, real])

    assert [root.path for root in sizes.roots] == [str(real)]


def test_long_paths_are_cut_to_200_characters(tmp_path: Path) -> None:
    root = tmp_path / "root"
    make_file(root / ("x" * 220), 100)

    root_size = FilesystemDiskBreakdown().directory_sizes([root]).roots[0]

    assert len(root_size.largest_files[0].path) == 200


def test_default_roots_are_absolute_and_configurable(tmp_path: Path) -> None:
    config = sentinel_config(tmp_path)

    assert config.disk_breakdown_roots == list(DEFAULT_DISK_BREAKDOWN_ROOTS)
    assert all(root.is_absolute() for root in config.disk_breakdown_roots)


def test_relative_disk_breakdown_root_is_rejected(tmp_path: Path) -> None:
    raw = sentinel_config(tmp_path).model_dump() | {"disk_breakdown_roots": ["relative/path"]}

    with pytest.raises(ValidationError):
        SentinelConfig.model_validate(raw)


@pytest.fixture
def recording() -> RecordingDiskBreakdown:
    return RecordingDiskBreakdown()


@pytest.fixture
def client(tmp_path: Path, recording: RecordingDiskBreakdown) -> TestClient:
    config = sentinel_config(tmp_path)
    store = NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300)
    app = create_app(
        config,
        FakeSystemctl(),
        store,
        config.load_secrets(),
        disk_breakdown=recording,
    )
    return TestClient(app)


def signed_post(client: TestClient, path: str, payload: dict[str, object]) -> httpx.Response:
    body = json.dumps(payload).encode()
    headers = sign_request(KEY_ID, SECRET, "POST", path, body).as_dict()
    return client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})


def test_directory_sizes_tool_uses_configured_roots(
    client: TestClient, recording: RecordingDiskBreakdown, tmp_path: Path
) -> None:
    body = signed_post(client, "/v1/tools/get_directory_sizes", {"args": {}}).json()

    assert body["ok"] is True
    assert body["data"] == {"roots": [], "complete": True, "scanned_entries": 0}
    assert recording.calls == [sentinel_config(tmp_path).disk_breakdown_roots]


def test_directory_sizes_tool_rejects_a_path_argument(
    client: TestClient, recording: RecordingDiskBreakdown
) -> None:
    body = signed_post(client, "/v1/tools/get_directory_sizes", {"args": {"path": "/"}}).json()

    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION"
    assert recording.calls == []


def test_directory_sizes_is_available_to_the_metrics_agent_only(tmp_path: Path) -> None:
    spec = next(
        tool
        for tool in build_read_tools(SentinelDirectory(tmp_path, httpx.AsyncClient()))
        if tool.name == "get_directory_sizes"
    )

    assert spec.agents == frozenset({"metrics"})
    assert spec.untrusted_fields == ("roots",)
