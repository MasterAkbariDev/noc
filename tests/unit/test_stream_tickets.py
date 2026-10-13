import logging

from noc.api.tickets import TicketRedactionFilter, TicketStore, redact_tickets_in_access_log


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_issued_ticket_is_consumed_once() -> None:
    store = TicketStore(clock=FakeClock())
    ticket = store.issue()
    assert store.consume(ticket) is True
    assert store.consume(ticket) is False


def test_unknown_ticket_is_rejected() -> None:
    store = TicketStore(clock=FakeClock())
    store.issue()
    assert store.consume("not-issued") is False


def test_ticket_expires_after_ttl() -> None:
    clock = FakeClock()
    store = TicketStore(clock=clock, ttl_seconds=30)
    ticket = store.issue()
    clock.now = 29.9
    assert store.consume(ticket) is True
    second = store.issue()
    clock.now = 60.0
    assert store.consume(second) is False


def test_capacity_evicts_oldest_ticket() -> None:
    store = TicketStore(clock=FakeClock(), capacity=3)
    oldest = store.issue()
    issued = [store.issue() for _ in range(3)]
    assert store.consume(oldest) is False
    assert all(store.consume(ticket) for ticket in issued)


def test_tickets_are_unique() -> None:
    store = TicketStore(clock=FakeClock())
    assert len({store.issue() for _ in range(50)}) == 50


def make_access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", 200),
        None,
    )


def test_access_log_filter_redacts_the_ticket() -> None:
    record = make_access_record("/api/events/stream?ticket=abc123_-XYZ&x=1")
    TicketRedactionFilter().filter(record)
    assert "abc123" not in record.getMessage()
    assert "ticket=REDACTED&x=1" in record.getMessage()


def test_access_log_filter_leaves_other_paths_alone() -> None:
    record = make_access_record("/api/incidents?status=OPEN")
    TicketRedactionFilter().filter(record)
    assert "/api/incidents?status=OPEN" in record.getMessage()


def test_redaction_is_installed_once() -> None:
    redact_tickets_in_access_log()
    redact_tickets_in_access_log()
    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(item, TicketRedactionFilter) for item in filters) == 1
