import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from noc_sentinel.app import create_app
from noc_sentinel.nonce_store import NonceStore
from noc_shared.signing import sign_request
from tests.support.builders import KEY_ID, SECRET, FakeSystemctl, sentinel_config


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    config = sentinel_config(tmp_path)
    store = NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300)
    app = create_app(config, FakeSystemctl(), store, config.load_secrets())
    return TestClient(app)


def signed_post(
    client: TestClient, path: str, payload: dict[str, object], nonce: str | None = None
):
    body = json.dumps(payload).encode()
    headers = sign_request(KEY_ID, SECRET, "POST", path, body, nonce=nonce).as_dict()
    return client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})


def test_health_needs_no_signature(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_unsigned_tool_call_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/tools/get_service_status", json={"args": {}})
    assert response.status_code == 401


def test_signed_tool_call_reads_service_status(client: TestClient) -> None:
    response = signed_post(
        client, "/v1/tools/get_service_status", {"args": {"resource_id": "svc:demo-shop"}}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["data"]["active_state"] == "failed"
    assert body["data"]["restarts"] == 3
    assert body["data"]["memory_bytes"] is None


def test_replayed_nonce_is_rejected(client: TestClient) -> None:
    payload = {"args": {"resource_id": "svc:demo-shop"}}
    first = signed_post(client, "/v1/tools/get_service_status", payload, nonce="n-1")
    second = signed_post(client, "/v1/tools/get_service_status", payload, nonce="n-1")
    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json()["detail"] == "replayed_nonce"


@pytest.mark.parametrize(
    ("resource_id", "code"),
    [("svc:unknown", "NOT_FOUND"), ("ctr:demo-db", "NOT_ALLOWED"), ("../etc/passwd", "VALIDATION")],
)
def test_only_registered_units_can_be_read(client: TestClient, resource_id: str, code: str) -> None:
    response = signed_post(
        client, "/v1/tools/get_service_status", {"args": {"resource_id": resource_id}}
    )
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == code


def test_there_is_no_mutation_endpoint(client: TestClient) -> None:
    response = signed_post(client, "/v1/actions/restart_service", {"args": {}})
    assert response.status_code == 404


def test_metrics_expose_service_state(client: TestClient) -> None:
    text = client.get("/metrics").text
    assert 'noc_service_up{resource="svc:demo-shop"} 0.0' in text
    assert "noc_sentinel_halted 0.0" in text


def test_halt_file_is_reported(tmp_path: Path) -> None:
    config = sentinel_config(tmp_path)
    config.halt_file.write_text("stop")
    store = NonceStore(tmp_path / "n.sqlite3", 300)
    client = TestClient(create_app(config, FakeSystemctl(), store, config.load_secrets()))
    headers = sign_request(KEY_ID, SECRET, "GET", "/v1/inventory", b"", datetime.now(UTC))
    assert client.get("/v1/inventory", headers=headers.as_dict()).json()["halted"] is True
