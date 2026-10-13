import json
import subprocess
from datetime import UTC, datetime
from typing import Protocol

from noc_shared.tools import JournalPriority, LogLine

JOURNALCTL_PATH = "/usr/bin/journalctl"
JOURNAL_TIMEOUT_SECONDS = 5
MESSAGE_MAX_CHARS = 500
MICROSECONDS_PER_SECOND = 1_000_000
BYTE_MAX = 255


class JournalReader(Protocol):
    def read(
        self, unit: str, since_minutes: int, max_lines: int, min_priority: JournalPriority
    ) -> list[LogLine]: ...


class SubprocessJournal:
    def read(
        self, unit: str, since_minutes: int, max_lines: int, min_priority: JournalPriority
    ) -> list[LogLine]:
        argv = [
            JOURNALCTL_PATH,
            "--unit",
            unit,
            "--since",
            f"-{since_minutes}min",
            "--priority",
            min_priority,
            "--lines",
            str(max_lines),
            "--output",
            "json",
            "--no-pager",
        ]
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            shell=False,
            timeout=JOURNAL_TIMEOUT_SECONDS,
            check=True,
        )
        return parse_journal_output(completed.stdout)


def parse_journal_output(output: str) -> list[LogLine]:
    entries = (parse_entry(line) for line in output.splitlines() if line.strip())
    return [entry for entry in entries if entry is not None]


def parse_entry(line: str) -> LogLine | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    message = message_text(record.get("MESSAGE"))
    if message is None:
        return None
    return LogLine(
        ts=journal_timestamp(record.get("__REALTIME_TIMESTAMP")),
        priority=priority_level(record.get("PRIORITY")),
        message=message[:MESSAGE_MAX_CHARS],
    )


def message_text(value: object) -> str | None:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(
        isinstance(byte, int) and 0 <= byte <= BYTE_MAX for byte in value
    ):
        return bytes(value).decode("utf-8", errors="replace")
    return None


def journal_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value.isdigit():
        return None
    try:
        moment = datetime.fromtimestamp(int(value) / MICROSECONDS_PER_SECOND, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.isoformat()


def priority_level(value: object) -> int | None:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
