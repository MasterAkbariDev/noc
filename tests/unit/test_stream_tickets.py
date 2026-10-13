from noc.api.tickets import TicketStore


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
