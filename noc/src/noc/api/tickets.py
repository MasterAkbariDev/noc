import hashlib
import logging
import re
import secrets
import time
from collections.abc import Callable

TICKET_TTL_SECONDS = 30
MAX_LIVE_TICKETS = 1000


def digest(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


class TicketStore:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = TICKET_TTL_SECONDS,
        capacity: int = MAX_LIVE_TICKETS,
    ) -> None:
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._expires_at: dict[str, float] = {}

    def issue(self) -> str:
        self._purge_expired()
        ticket = secrets.token_urlsafe(32)
        self._expires_at[digest(ticket)] = self._clock() + self._ttl_seconds
        while len(self._expires_at) > self._capacity:
            del self._expires_at[next(iter(self._expires_at))]
        return ticket

    def consume(self, ticket: str) -> bool:
        expires_at = self._expires_at.pop(digest(ticket), None)
        return expires_at is not None and self._clock() < expires_at

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [key for key, expires_at in self._expires_at.items() if expires_at <= now]
        for key in expired:
            del self._expires_at[key]


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
