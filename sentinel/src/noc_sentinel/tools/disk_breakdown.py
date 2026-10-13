import os
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from noc_shared.tools import DirectorySizes, PathSize, RootSize

MAX_SCANNED_ENTRIES = 300_000
MAX_SCAN_SECONDS = 4.0
TOP_CHILDREN = 8
TOP_FILES = 8
PATH_MAX_CHARS = 200
BLOCK_BYTES = 512

ListDirectory = Callable[[str], list[os.DirEntry[str]]]


def read_directory(path: str) -> list[os.DirEntry[str]]:
    with os.scandir(path) as entries:
        return list(entries)


class DiskBreakdownReader(Protocol):
    def directory_sizes(self, roots: list[Path]) -> DirectorySizes: ...


@dataclass(frozen=True)
class Entry:
    path: str
    size: int
    parent: int | None
    is_directory: bool


@dataclass(frozen=True)
class Walk:
    entries: list[Entry]
    root_readable: bool
    all_readable: bool


class ScanBudget:
    def __init__(self, max_entries: int, max_seconds: float) -> None:
        self._entries_left = max_entries
        self._deadline = time.monotonic() + max_seconds
        self.scanned = 0
        self.exhausted = False

    def take(self) -> bool:
        if self._entries_left <= 0 or time.monotonic() > self._deadline:
            self.exhausted = True
            return False
        self._entries_left -= 1
        self.scanned += 1
        return True


class FilesystemDiskBreakdown:
    def __init__(
        self,
        list_directory: ListDirectory = read_directory,
        max_entries: int = MAX_SCANNED_ENTRIES,
        max_seconds: float = MAX_SCAN_SECONDS,
    ) -> None:
        self._list_directory = list_directory
        self._max_entries = max_entries
        self._max_seconds = max_seconds

    def directory_sizes(self, roots: list[Path]) -> DirectorySizes:
        budget = ScanBudget(self._max_entries, self._max_seconds)
        existing = [root for root in roots if root.is_dir() and not root.is_symlink()]
        root_sizes = [self._root_size(root, budget) for root in existing]
        return DirectorySizes(
            roots=root_sizes, complete=not budget.exhausted, scanned_entries=budget.scanned
        )

    def _root_size(self, root: Path, budget: ScanBudget) -> RootSize:
        walk = self._walk(root, budget)
        totals = subtree_totals(walk.entries)
        return RootSize(
            path=truncate(str(root)),
            total_bytes=totals[0] if walk.root_readable else None,
            readable=walk.root_readable and walk.all_readable,
            largest_children=largest_children(walk.entries, totals),
            largest_files=largest_files(walk.entries),
        )

    def _walk(self, root: Path, budget: ScanBudget) -> Walk:
        try:
            root_stat = os.lstat(root)
        except OSError:
            return Walk(entries=[], root_readable=False, all_readable=False)
        entries = [Entry(str(root), allocated_bytes(root_stat), None, True)]
        pending = [0]
        root_readable = True
        all_readable = True
        while pending and not budget.exhausted:
            parent = pending.pop()
            try:
                children = self._list_directory(entries[parent].path)
            except OSError:
                all_readable = False
                if parent == 0:
                    root_readable = False
                continue
            for child in children:
                if not budget.take():
                    break
                add_child(entries, pending, child, parent, root_stat.st_dev)
        return Walk(entries=entries, root_readable=root_readable, all_readable=all_readable)


def add_child(
    entries: list[Entry],
    pending: list[int],
    child: os.DirEntry[str],
    parent: int,
    root_device: int,
) -> None:
    try:
        child_stat = child.stat(follow_symlinks=False)
    except OSError:
        return
    if child_stat.st_dev != root_device:
        return
    is_directory = stat.S_ISDIR(child_stat.st_mode)
    entries.append(Entry(child.path, allocated_bytes(child_stat), parent, is_directory))
    if is_directory:
        pending.append(len(entries) - 1)


def allocated_bytes(file_stat: os.stat_result) -> int:
    return file_stat.st_blocks * BLOCK_BYTES


def subtree_totals(entries: list[Entry]) -> list[int]:
    totals = [entry.size for entry in entries]
    for index in range(len(entries) - 1, 0, -1):
        parent = entries[index].parent
        if parent is not None:
            totals[parent] += totals[index]
    return totals


def largest_children(entries: list[Entry], totals: list[int]) -> list[PathSize]:
    children = [index for index, entry in enumerate(entries) if entry.parent == 0]
    ranked = sorted(children, key=lambda index: totals[index], reverse=True)[:TOP_CHILDREN]
    return [
        PathSize(path=truncate(entries[index].path), size_bytes=totals[index]) for index in ranked
    ]


def largest_files(entries: list[Entry]) -> list[PathSize]:
    files = [entry for entry in entries if not entry.is_directory]
    ranked = sorted(files, key=lambda entry: entry.size, reverse=True)[:TOP_FILES]
    return [PathSize(path=truncate(entry.path), size_bytes=entry.size) for entry in ranked]


def truncate(path: str) -> str:
    return path[:PATH_MAX_CHARS]
