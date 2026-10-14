import hashlib
import logging
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

TICKET_TTL_SECONDS = 30
MAX_LIVE_TICKETS = 1000
MAX_TICKETS_PER_SESSION = 5


def digest(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


@dataclass(frozen=True)
class TicketGrant:
    session_hash: str | None


@dataclass(frozen=True)
class LiveTicket:
    expires_at: float
    session_hash: str | None


class TicketStore:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = TICKET_TTL_SECONDS,
        capacity: int = MAX_LIVE_TICKETS,
        per_session: int = MAX_TICKETS_PER_SESSION,
    ) -> None:
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._per_session = per_session
        self._live: dict[str, LiveTicket] = {}

    def issue(self, session_hash: str | None = None) -> str:
        self._purge_expired()
        if session_hash is not None:
            self._limit_session(session_hash)
        ticket = secrets.token_urlsafe(32)
        self._live[digest(ticket)] = LiveTicket(self._clock() + self._ttl_seconds, session_hash)
        while len(self._live) > self._capacity:
            del self._live[next(iter(self._live))]
        return ticket

    def consume(self, ticket: str) -> TicketGrant | None:
        live = self._live.pop(digest(ticket), None)
        if live is None or self._clock() >= live.expires_at:
            return None
        return TicketGrant(live.session_hash)

    def _limit_session(self, session_hash: str) -> None:
        owned = [key for key, live in self._live.items() if live.session_hash == session_hash]
        for key in owned[: max(0, len(owned) - self._per_session + 1)]:
            del self._live[key]

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [key for key, live in self._live.items() if live.expires_at <= now]
        for key in expired:
            del self._live[key]


TICKET_QUERY = re.compile(r"([?&]ticket=)[^&\s\"]*")
REDACTED = "REDACTED"


class TicketRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and any(isinstance(arg, str) for arg in args):
            record.args = tuple(
                TICKET_QUERY.sub(rf"\g<1>{REDACTED}", arg) if isinstance(arg, str) else arg
                for arg in args
            )
        return True


def redact_tickets_in_access_log() -> None:
    access_log = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, TicketRedactionFilter) for item in access_log.filters):
        access_log.addFilter(TicketRedactionFilter())
