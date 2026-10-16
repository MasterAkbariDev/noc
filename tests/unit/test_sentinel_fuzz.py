import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from noc_sentinel.actions import PROTECTED_UNITS
from noc_sentinel.app import create_app
from noc_sentinel.config import ActionsConfig, SentinelConfig
from noc_sentinel.nonce_store import NonceStore
from noc_shared.actions import ActionType, compute_action_hash
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.signing import sign_request
from tests.support.builders import DEMO_SHOP, KEY_ID, SECRET, FakeSystemctl, sentinel_config

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
TARGET = "demo-1"
INCIDENT = UUID("7d3c1f0e-2b8a-4c6d-9e51-0a1b2c3d4e5f")
UNIT = "demo-shop.service"
ALLOWED_ARGV = {
    ("/usr/bin/systemctl", "restart", UNIT),
    ("/usr/bin/systemctl", "start", UNIT),
}
TOOL_NAMES = ["get_service_status", "get_disk_usage", "get_service_logs", "nope", "../x", ""]
FUZZ_EXAMPLES = 120
ACTION_TYPES: list[ActionType] = ["restart_service", "start_service"]

json_scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
json_values = st.recursive(
    json_scalars,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=12), inner, max_size=4)
    ),
    max_leaves=12,
)
fuzz_settings = settings(
    max_examples=FUZZ_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class RecordingRunner:
    def __init__(self, systemctl: FakeSystemctl) -> None:
        self.systemctl = systemctl
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        self.calls.append(argv)
        self.systemctl.active_state = "active"
        return 0


def build_config(directory: Path) -> SentinelConfig:
    base = sentinel_config(directory)
    extra = [
        ManagedResource(
            id="svc:sshd",
            kind=ResourceKind.SYSTEMD_UNIT,
            name="sshd.service",
            allowed_actions=["restart_service", "start_service"],
        ),
        ManagedResource(
            id="svc:systemd-resolved",
            kind=ResourceKind.SYSTEMD_UNIT,
            name="systemd-resolved.service",
            allowed_actions=["restart_service"],
        ),
    ]
    shop = base.resource(DEMO_SHOP)
    assert shop is not None
    enabled = shop.model_copy(update={"allowed_actions": ["restart_service", "start_service"]})
    return base.model_copy(
        update={
            "actions": ActionsConfig(enabled=True, max_per_resource_per_hour=2),
            "resources": [enabled, *[r for r in base.resources if r.id != DEMO_SHOP], *extra],
        }
    )


@pytest.fixture(scope="module")
def harness() -> tuple[TestClient, RecordingRunner, SentinelConfig]:
    directory = Path(tempfile.mkdtemp(prefix="sentinel-fuzz-"))
    config = build_config(directory)
    systemctl = FakeSystemctl(active_state="failed")
    runner = RecordingRunner(systemctl)
    app = create_app(
        config,
        systemctl,
        NonceStore(directory / "nonces.sqlite3", ttl_seconds=300),
        config.load_secrets(),
        clock=lambda: NOW,
        action_runner=runner,
    )
    return TestClient(app, raise_server_exceptions=False), runner, config


def signed_post(client: TestClient, path: str, body: bytes) -> httpx.Response:
    headers = sign_request(KEY_ID, SECRET, "POST", path, body, now=NOW).as_dict()
    return client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})


def action_request(
    resource_id: str,
    attempt: int = 1,
    action_hash: str | None = None,
    action_type: ActionType = "restart_service",
) -> dict[str, Any]:
    return {
        "action_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "incident_id": str(INCIDENT),
        "attempt": attempt,
        "action_hash": action_hash
        or compute_action_hash(action_type, TARGET, resource_id, {}, INCIDENT, attempt),
        "resource_id": resource_id,
        "approval_id": str(uuid4()),
    }


@fuzz_settings
@given(tool=st.sampled_from(TOOL_NAMES), payload=json_values)
def test_signed_tool_calls_with_any_body_never_cause_a_server_error(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], tool: str, payload: object
) -> None:
    client, _, _ = harness
    body = json.dumps(payload).encode()
    response = signed_post(client, f"/v1/tools/{tool}", body)
    assert response.status_code < 500


@fuzz_settings
@given(resource_id=st.text(max_size=80))
def test_arbitrary_resource_ids_are_never_read_unless_registered(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], resource_id: str
) -> None:
    client, _, config = harness
    body = json.dumps({"args": {"resource_id": resource_id}}).encode()
    response = signed_post(client, "/v1/tools/get_service_status", body)
    assert response.status_code < 500
    answer = response.json()
    if answer.get("ok") is True:
        assert config.resource(resource_id) is not None


@fuzz_settings
@given(
    payload=json_values,
    action=st.sampled_from(["restart_service", "start_service", "stop_service", "rm", ""]),
)
def test_signed_action_calls_with_any_body_never_cause_a_server_error(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], payload: object, action: str
) -> None:
    client, _, _ = harness
    response = signed_post(client, f"/v1/actions/{action}", json.dumps(payload).encode())
    assert response.status_code < 500


@fuzz_settings
@given(
    resource_id=st.text(max_size=60),
    attempt=st.integers(min_value=1, max_value=10),
    action=st.sampled_from(ACTION_TYPES),
)
def test_a_well_formed_action_never_runs_anything_outside_the_allowlist(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
    resource_id: str,
    attempt: int,
    action: str,
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    response = signed_post(
        client,
        f"/v1/actions/{action}",
        json.dumps(action_request(resource_id, attempt, action_type=action)).encode(),
    )
    assert response.status_code < 500
    assert set(runner.calls[before:]) <= ALLOWED_ARGV


@pytest.mark.parametrize("resource_id", ["svc:sshd", "svc:systemd-resolved"])
def test_a_validly_signed_request_for_a_protected_unit_is_refused(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], resource_id: str
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    response = signed_post(
        client, "/v1/actions/restart_service", json.dumps(action_request(resource_id)).encode()
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PROTECTED"
    assert len(runner.calls) == before


def test_protected_units_in_the_test_config_are_really_on_the_protected_list() -> None:
    assert "sshd.service" in PROTECTED_UNITS
    assert "systemd-resolved.service".startswith("systemd-")


@pytest.mark.parametrize(
    "resource_id", ["svc:not-registered", "ctr:demo-db", "host:demo-1", "../../etc"]
)
def test_a_validly_signed_request_for_an_unregistered_resource_is_refused(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], resource_id: str
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    response = signed_post(
        client, "/v1/actions/restart_service", json.dumps(action_request(resource_id)).encode()
    )
    assert response.status_code in {403, 422}
    assert len(runner.calls) == before


def test_an_unknown_action_type_is_a_404_even_when_signed(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    response = signed_post(
        client, "/v1/actions/reboot_host", json.dumps(action_request(DEMO_SHOP)).encode()
    )
    assert response.status_code == 404
    assert len(runner.calls) == before


def test_a_hash_for_another_resource_is_refused(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    other_hash = compute_action_hash("restart_service", TARGET, "svc:sshd", {}, INCIDENT, 1)
    response = signed_post(
        client,
        "/v1/actions/restart_service",
        json.dumps(action_request(DEMO_SHOP, action_hash=other_hash)).encode(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "HASH_MISMATCH"
    assert len(runner.calls) == before


def test_throttling_stops_a_flood_of_signed_restarts(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, runner, config = harness
    limit = config.actions.max_per_resource_per_hour
    statuses = [
        signed_post(
            client,
            "/v1/actions/restart_service",
            json.dumps(action_request(DEMO_SHOP, attempt=(index % 10) + 1)).encode(),
        ).status_code
        for index in range(limit + 6)
    ]
    assert 429 in statuses or statuses.count(200) <= limit
    assert len([call for call in runner.calls if call[1] == "restart"]) <= limit + 3


def test_unsigned_and_wrongly_signed_action_calls_are_401(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, runner, _ = harness
    before = len(runner.calls)
    body = json.dumps(action_request(DEMO_SHOP)).encode()
    unsigned = client.post("/v1/actions/restart_service", content=body)
    forged = sign_request(
        "unknown-key", b"x" * 32, "POST", "/v1/actions/restart_service", body, now=NOW
    )
    wrong = client.post("/v1/actions/restart_service", content=body, headers=forged.as_dict())
    assert unsigned.status_code == 401
    assert wrong.status_code == 401
    assert len(runner.calls) == before


@pytest.mark.parametrize("body", [b"Infinity", b"-Infinity", b"NaN"])
def test_non_finite_numbers_in_a_signed_body_get_a_422_not_a_500(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig], body: bytes
) -> None:
    client, _, _ = harness
    response = signed_post(client, "/v1/tools/get_service_status", body)
    assert response.status_code == 422


def test_a_validation_error_does_not_echo_the_request_back(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, _, _ = harness
    secret_text = "do-not-echo-this-value"
    response = signed_post(
        client, "/v1/tools/get_service_status", json.dumps({"args": secret_text}).encode()
    )
    assert response.status_code == 422
    assert secret_text not in response.text


def test_a_non_finite_number_inside_valid_arguments_is_a_tool_validation_error(
    harness: tuple[TestClient, RecordingRunner, SentinelConfig],
) -> None:
    client, _, _ = harness
    response = signed_post(client, "/v1/tools/get_service_status", b'{"args": {"x": NaN}}')
    assert response.status_code == 200
    assert response.json()["ok"] is False
