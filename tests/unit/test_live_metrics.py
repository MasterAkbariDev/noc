from noc.api.live_metrics import WINDOWS, points_for, service_rows, value_for
from noc.api.prometheus import Sample, Series, finite_points


def series(target: str, points: list[tuple[float, float]], **labels: str) -> Series:
    return Series(labels={"target": target, **labels}, points=points)


def test_each_range_keeps_the_chart_between_sixty_and_one_hundred_fifty_points() -> None:
    for window in WINDOWS.values():
        assert 60 <= window.seconds // window.step <= 150


def test_points_belong_to_the_named_server_only() -> None:
    readings = [series("alpha", [(1.0, 10.0)]), series("zeta", [(1.0, 90.0)])]
    assert points_for(readings, "zeta") == [(1.0, 90.0)]
    assert points_for(readings, "missing") == []
    assert points_for(None, "zeta") == []


def test_values_that_are_not_numbers_are_dropped() -> None:
    assert finite_points([(1.0, "5"), (2.0, "NaN"), (3.0, "+Inf"), (4.0, "7.5")]) == [
        (1.0, 5.0),
        (4.0, 7.5),
    ]


def test_an_instant_value_is_read_for_the_named_server() -> None:
    samples = [Sample(labels={"target": "alpha"}, value=3600.0)]
    assert value_for(samples, "alpha") == 3600.0
    assert value_for(samples, "zeta") is None


def test_services_join_state_memory_and_limit_by_resource() -> None:
    up = [
        Sample(labels={"target": "alpha", "resource": "svc:shop"}, value=1.0),
        Sample(labels={"target": "alpha", "resource": "svc:reports"}, value=0.0),
        Sample(labels={"target": "zeta", "resource": "svc:other"}, value=1.0),
    ]
    memory = [series("alpha", [(1.0, 2048.0)], resource="svc:shop")]
    limits = [Sample(labels={"target": "alpha", "resource": "svc:shop"}, value=4096.0)]
    rows = service_rows("alpha", up, memory, limits)
    assert [(row.name, row.up, row.memory_limit_bytes) for row in rows] == [
        ("reports", False, None),
        ("shop", True, 4096.0),
    ]
    assert rows[1].memory_bytes == [(1.0, 2048.0)]


def test_a_service_seen_only_in_memory_has_an_unknown_state() -> None:
    memory = [series("alpha", [(1.0, 1.0)], resource="svc:shop")]
    assert service_rows("alpha", None, memory, None)[0].up is None
