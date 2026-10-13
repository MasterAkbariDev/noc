import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from noc_shared.actions import ActionRequest, ActionType, compute_action_hash

INCIDENT = uuid.UUID("7d3c1f0e-2b8a-4c6d-9e51-0a1b2c3d4e5f")
HEX_DIGITS = set("0123456789abcdef")


def digest(
    action_type: ActionType = "restart_service",
    target: str = "demo-1",
    resource_id: str = "svc:demo-shop",
    params: dict[str, str | int] | None = None,
    incident_id: uuid.UUID = INCIDENT,
    attempt: int = 1,
) -> str:
    return compute_action_hash(
        action_type,
        target,
        resource_id,
        params if params is not None else {"reason": "stuck", "timeout": 30},
        incident_id,
        attempt,
    )


def request_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "action_id": uuid.uuid4(),
        "attempt_id": uuid.uuid4(),
        "incident_id": INCIDENT,
        "attempt": 1,
        "action_hash": "a" * 64,
        "resource_id": "svc:demo-shop",
        "approval_id": uuid.uuid4(),
    }
    fields.update(overrides)
    return fields


def test_hash_is_64_lowercase_hex_and_stable() -> None:
    first = digest()
    assert len(first) == 64
    assert set(first) <= HEX_DIGITS
    assert first == digest()


def test_params_order_does_not_change_hash() -> None:
    assert digest(params={"reason": "stuck", "timeout": 30}) == digest(
        params={"timeout": 30, "reason": "stuck"}
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"action_type": "start_service"},
        {"target": "demo-2"},
        {"resource_id": "svc:other"},
        {"params": {"reason": "other", "timeout": 30}},
        {"incident_id": uuid.uuid4()},
        {"attempt": 2},
    ],
)
def test_every_bound_field_changes_the_hash(changed: dict[str, Any]) -> None:
    assert digest(**changed) != digest()


def test_request_requires_exactly_one_authority() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(**request_fields(auto_policy_ref="policy-1"))
    with pytest.raises(ValidationError):
        ActionRequest(**request_fields(approval_id=None))
    assert ActionRequest(**request_fields(approval_id=None, auto_policy_ref="policy-1"))


def test_auto_policy_ref_is_capped_at_80_characters() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(**request_fields(approval_id=None, auto_policy_ref="p" * 81))


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(**request_fields(action_type="restart_service"))
