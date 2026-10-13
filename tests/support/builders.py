import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from noc.agents.schemas import InvestigationReport
from noc.detection.alerts import PrometheusAlert
from noc.tools.spec import TargetRef, ToolContext
from noc_sentinel.config import SentinelConfig
from noc_shared.resources import ManagedResource, ResourceKind

KEY_ID = "noc-test-key"
SECRET = b"0123456789abcdef0123456789abcdef"
DEMO_SHOP = "svc:demo-shop"


def sentinel_config(tmp_path: Path, environment: str = "lab") -> SentinelConfig:
    key_file = tmp_path / f"{KEY_ID}.key"
    key_file.write_bytes(SECRET)
    return SentinelConfig(
        target="demo-1",
        environment=environment,
        key_files={KEY_ID: key_file},
        state_dir=tmp_path,
        halt_file=tmp_path / "HALT",
        resources=[
            ManagedResource(
                id=DEMO_SHOP,
                kind=ResourceKind.SYSTEMD_UNIT,
                name="demo-shop.service",
                allowed_actions=("restart_service", "start_service"),
            ),
            ManagedResource(id="ctr:demo-db", kind=ResourceKind.CONTAINER, name="demo-db"),
        ],
    )


class FakeSystemctl:
    def __init__(self, active_state: str = "failed") -> None:
        self.active_state = active_state
        self.calls: list[str] = []

    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        self.calls.append(unit)
        return {
            "ActiveState": self.active_state,
            "SubState": "dead" if self.active_state != "active" else "running",
            "NRestarts": "3",
            "ExecMainStatus": "137" if self.active_state != "active" else "0",
            "ActiveEnterTimestamp": "",
            "MemoryCurrent": "[not set]",
        }


def tool_context(agent: str = "investigator", data_policy: str = "full") -> ToolContext:
    target = TargetRef(
        id=uuid.uuid4(),
        name="demo-1",
        sentinel_url="https://demo-1:9443",
        hmac_key_id=KEY_ID,
        environment="lab",
        data_policy=data_policy,
    )
    return ToolContext(incident_id=uuid.uuid4(), agent=agent, target=target, trace_id="a" * 32)


def prometheus_alert(
    alertname: str = "ServiceDown",
    target: str = "demo-1",
    resource: str = DEMO_SHOP,
    severity: str = "critical",
) -> PrometheusAlert:
    return PrometheusAlert.model_validate(
        {
            "labels": {
                "alertname": alertname,
                "target": target,
                "resource": resource,
                "severity": severity,
            },
            "annotations": {"summary": f"{resource} is not active"},
            "state": "firing",
            "activeAt": datetime(2026, 10, 13, 9, 0, tzinfo=UTC).isoformat(),
            "value": "0e+00",
        }
    )


def investigation_payload(
    excerpt: str = '"active_state": "failed"',
    code: str = "service_crashed",
    confidence: float = 0.9,
    resource: str | None = DEMO_SHOP,
) -> dict[str, Any]:
    payload = {
        "findings": [
            {
                "id": "F1",
                "category": "service",
                "summary": "demo-shop.service is failed after being killed (exit 137).",
                "severity": "critical",
                "evidence": [{"tool_call_ref": "T1", "excerpt": excerpt}],
                "evidence_strength": "direct",
                "counter_evidence": [],
                "confidence": 0.95,
                "suspected_injection": False,
            }
        ],
        "diagnosis": {
            "hypotheses": [
                {
                    "root_cause_code": code,
                    "description": "The service process died and systemd did not restart it.",
                    "confidence": confidence,
                    "supporting_findings": ["F1"],
                    "contradicting_findings": [],
                    "affected_resource_id": resource,
                }
            ],
            "is_security_incident": False,
            "needs_more_info": [],
        },
    }
    InvestigationReport.model_validate(payload)
    return payload
