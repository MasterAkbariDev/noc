import ipaddress
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

import psutil

from noc_sentinel.tools.journal import (
    JOURNAL_TIMEOUT_SECONDS,
    JOURNALCTL_PATH,
    parse_journal_output,
)
from noc_shared.tools import ActiveSessions, AuthEvents, AuthSource, LogLine, Session

AuthCommand = Literal["sshd", "sudo"]
AuthOutcome = Literal["failed", "accepted"]

AUTH_LINES_MAX = 5000
AUTH_SOURCES_MAX = 20
SESSIONS_MAX = 20
STRING_MAX_CHARS = 200
USERNAME_MAX_CHARS = 64
ADDRESS_MAX_CHARS = 45

FAILED_PATTERN = re.compile(
    r"Failed (?:password|publickey) for (?P<invalid>invalid user )?"
    r"(?P<user>\S{1,64}) from (?P<ip>[0-9a-fA-F:.]{2,45}) port \d+"
)
ACCEPTED_PATTERN = re.compile(
    r"Accepted (?:password|publickey) for (?P<user>\S{1,64}) "
    r"from (?P<ip>[0-9a-fA-F:.]{2,45}) port \d+"
)


class AuthLogReader(Protocol):
    def read(self, command: AuthCommand, since_minutes: int, max_lines: int) -> list[LogLine]: ...


class SessionReader(Protocol):
    def sessions(self) -> list[Session]: ...


class SubprocessAuthLog:
    def read(self, command: AuthCommand, since_minutes: int, max_lines: int) -> list[LogLine]:
        argv = [
            JOURNALCTL_PATH,
            f"_COMM={command}",
            "--since",
            f"-{since_minutes}min",
            "--output",
            "json",
            "--no-pager",
            "--lines",
            str(max_lines),
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


class PsutilSessionReader:
    def sessions(self) -> list[Session]:
        return [
            Session(
                username=user.name,
                terminal=user.terminal,
                host=user.host,
                started_at=datetime.fromtimestamp(user.started, UTC).isoformat(),
            )
            for user in psutil.users()
        ]


@dataclass(frozen=True)
class AuthAttempt:
    outcome: AuthOutcome
    username: str
    address: str
    invalid_user: bool
    ts: str | None


def parse_auth_line(line: LogLine) -> AuthAttempt | None:
    failed = FAILED_PATTERN.match(line.message)
    if failed is not None:
        return attempt_from(
            "failed", failed.group("user"), failed.group("ip"), failed.group("invalid"), line.ts
        )
    accepted = ACCEPTED_PATTERN.match(line.message)
    if accepted is not None:
        return attempt_from("accepted", accepted.group("user"), accepted.group("ip"), None, line.ts)
    return None


def attempt_from(
    outcome: AuthOutcome, username: str, address: str, invalid: str | None, ts: str | None
) -> AuthAttempt | None:
    if not is_ip_address(address):
        return None
    return AuthAttempt(
        outcome=outcome,
        username=username[:USERNAME_MAX_CHARS],
        address=address[:ADDRESS_MAX_CHARS],
        invalid_user=invalid is not None,
        ts=ts,
    )


def is_ip_address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def parse_auth_attempts(lines: list[LogLine]) -> list[AuthAttempt]:
    attempts = (parse_auth_line(line) for line in lines)
    return [attempt for attempt in attempts if attempt is not None]


def top_sources(attempts: list[AuthAttempt]) -> list[AuthSource]:
    groups: dict[tuple[str, str], list[AuthAttempt]] = {}
    for attempt in attempts:
        groups.setdefault((attempt.address, attempt.username), []).append(attempt)
    sources = [source_from(key, items) for key, items in groups.items()]
    sources.sort(key=lambda source: (-source.count, source.address, source.username))
    return sources[:AUTH_SOURCES_MAX]


def source_from(key: tuple[str, str], items: list[AuthAttempt]) -> AuthSource:
    stamps = [item.ts for item in items if item.ts is not None]
    return AuthSource(
        address=key[0],
        username=key[1],
        count=len(items),
        first_seen=min(stamps, default=None),
        last_seen=max(stamps, default=None),
    )


def auth_events(sshd_lines: list[LogLine], sudo_lines: list[LogLine]) -> AuthEvents:
    attempts = parse_auth_attempts(sshd_lines)
    failed = [attempt for attempt in attempts if attempt.outcome == "failed"]
    accepted = [attempt for attempt in attempts if attempt.outcome == "accepted"]
    return AuthEvents(
        failed=top_sources(failed),
        accepted=top_sources(accepted),
        sudo_events=len(sudo_lines),
        invalid_user_attempts=sum(1 for attempt in failed if attempt.invalid_user),
        truncated=len(sshd_lines) >= AUTH_LINES_MAX,
    )


def active_sessions(sessions: list[Session]) -> ActiveSessions:
    return ActiveSessions(
        sessions=[bounded_session(session) for session in sessions[:SESSIONS_MAX]]
    )


def bounded_session(session: Session) -> Session:
    return Session(
        username=session.username[:STRING_MAX_CHARS],
        terminal=bounded_optional(session.terminal),
        host=bounded_optional(session.host),
        started_at=session.started_at[:STRING_MAX_CHARS],
    )


def bounded_optional(text: str | None) -> str | None:
    return None if text is None else text[:STRING_MAX_CHARS]
