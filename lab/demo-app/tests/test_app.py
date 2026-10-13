from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from demo_app.chaos import ChaosSettings, ChaosState
from demo_app.main import ChaosListener, PaymentsStub, build_shop
from demo_app.reports import run_once, summarise
from demo_app.settings import CHAOS_HOST, Settings
from demo_app.store import ProductStore


class FakeCursor:
    def fetchall(self) -> list[tuple[object, ...]]:
        return [(1, "Mug", 900)]


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, query: str) -> FakeCursor:
        return FakeCursor()

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def fake_connect(opened: list[FakeConnection]) -> Callable[[str], FakeConnection]:
    def connect(database_url: str) -> FakeConnection:
        connection = FakeConnection()
        opened.append(connection)
        return connection

    return connect


def clients() -> tuple[TestClient, TestClient]:
    apps = build_shop(Settings())
    return TestClient(apps.public), TestClient(apps.chaos)


def route_paths(app: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "")) for route in app.routes}


def test_products_fall_back_to_static_list_without_database() -> None:
    public, _ = clients()
    response = public.get("/products")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Mug"


def test_checkout_totals_the_order() -> None:
    public, _ = clients()
    response = public.post("/checkout", json={"product_id": 2, "quantity": 2})
    assert response.status_code == 200
    assert response.json()["total_cents"] == 5000
    assert response.json()["status"] == "approved"


def test_checkout_rejects_unknown_product_and_bad_quantity() -> None:
    public, _ = clients()
    assert public.post("/checkout", json={"product_id": 99}).status_code == 404
    assert public.post("/checkout", json={"product_id": 1, "quantity": 0}).status_code == 422


def test_metrics_use_route_templates() -> None:
    public, _ = clients()
    public.get("/")
    body = public.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/",status="200"}' in body
    assert "http_request_duration_seconds_bucket" in body


def test_chaos_routes_are_not_on_the_public_app() -> None:
    apps = build_shop(Settings())
    assert not any(path.startswith("/chaos") for path in route_paths(apps.public))
    public = TestClient(apps.public)
    assert public.get("/chaos").status_code == 404
    assert public.post("/chaos/reset").status_code == 404
    assert public.put("/chaos", json={}).status_code == 404


def test_chaos_listener_binds_loopback_only() -> None:
    apps = build_shop(Settings())
    listener = ChaosListener(apps.chaos, 8099)
    assert CHAOS_HOST == "127.0.0.1"
    assert listener._server.config.host == "127.0.0.1"


def test_memory_leak_toggle_changes_behaviour() -> None:
    public, chaos = clients()
    assert chaos.put("/chaos", json={"memory_leak": True}).status_code == 200
    public.get("/products")
    public.get("/products")
    assert chaos.get("/chaos").json()["leaked_memory_mib"] == 2
    reset = chaos.post("/chaos/reset").json()
    assert reset["leaked_memory_mib"] == 0
    assert reset["memory_leak"] is False


def test_upstream_delay_is_validated_and_reported() -> None:
    _, chaos = clients()
    assert chaos.put("/chaos", json={"upstream_delay_ms": 250}).json()["upstream_delay_ms"] == 250
    assert chaos.put("/chaos", json={"upstream_delay_ms": 999999}).status_code == 422


def test_payments_stub_sleeps_for_configured_delay() -> None:
    slept: list[float] = []
    stub = PaymentsStub(sleep=slept.append)
    stub.charge(delay_ms=250)
    stub.charge(delay_ms=0)
    assert slept == [0.25]


def test_connection_leak_keeps_connections_checked_out() -> None:
    state = ChaosState()
    opened: list[FakeConnection] = []
    store = ProductStore("postgresql://demo", fake_connect(opened), state)
    state.replace_settings(ChaosSettings(connection_leak=True))
    store.list_products()
    store.list_products()
    assert REGISTRY.get_sample_value("demo_shop_db_connections_in_use") == 2
    assert not any(connection.closed for connection in opened)
    store.release_leaked()
    assert REGISTRY.get_sample_value("demo_shop_db_connections_in_use") == 0
    assert all(connection.closed for connection in opened)


def test_connections_are_returned_without_leak() -> None:
    opened: list[FakeConnection] = []
    store = ProductStore("postgresql://demo", fake_connect(opened), ChaosState())
    assert [item.name for item in store.list_products()] == ["Mug"]
    assert REGISTRY.get_sample_value("demo_shop_db_connections_in_use") == 0
    assert all(connection.closed for connection in opened)


def test_settings_read_environment() -> None:
    empty = Settings.from_env({"DEMO_DATABASE_URL": ""})
    assert empty.database_url is None
    assert empty.chaos_port == 8099
    configured = Settings.from_env(
        {"DEMO_DATABASE_URL": "postgresql://demo", "DEMO_CHAOS_PORT": "9000"}
    )
    assert configured.database_url == "postgresql://demo"
    assert configured.chaos_port == 9000


def test_reports_summarise_static_catalogue() -> None:
    store = ProductStore(None, fake_connect([]), ChaosState())
    assert summarise(store) == "products=3 catalogue_value_cents=3800"
    run_once(store, None)
