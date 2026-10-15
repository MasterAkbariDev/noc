import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from noc.agents.schemas import InvestigationReport
from noc.detection.alerts import PrometheusAlert
from noc.tools.spec import TargetRef, ToolContext
from noc_sentinel.config import SentinelConfig
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.tools import (
    CpuUsage,
    DiskUsage,
    JournalPriority,
    LogLine,
    MemoryUsage,
    MountUsage,
    ProcessInfo,
    ProcessSort,
)

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
                allowed_actions=("restart_service", "start_service", "chaos_service_down"),
            ),
            ManagedResource(id="ctr:demo-db", kind=ResourceKind.CONTAINER, name="demo-db"),
        ],
    )


class FakeSystemctl:
    def __init__(
        self,
        active_state: str = "failed",
        memory_current: str = "[not set]",
        memory_max: str = "infinity",
    ) -> None:
        self.active_state = active_state
        self.memory_current = memory_current
        self.memory_max = memory_max
        self.calls: list[str] = []

    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        self.calls.append(unit)
        return {
            "ActiveState": self.active_state,
            "SubState": "dead" if self.active_state != "active" else "running",
            "NRestarts": "3",
            "ExecMainStatus": "137" if self.active_state != "active" else "0",
            "ActiveEnterTimestamp": "",
            "MemoryCurrent": self.memory_current,
            "MemoryMax": self.memory_max,
        }


class FakeHostReader:
    def __init__(self, process_names: tuple[str, ...] = ("demo-shop",)) -> None:
        self.process_names = process_names
        self.process_calls: list[tuple[str, int]] = []

    def cpu(self) -> CpuUsage:
        return CpuUsage(
            percent=37.5,
            per_core_percent=[30.0, 45.0],
            steal_percent=0.0,
            iowait_percent=1.2,
            load_1m=0.8,
            load_5m=0.6,
            load_15m=0.5,
        )

    def memory(self) -> MemoryUsage:
        return MemoryUsage(
            total_bytes=4_000_000_000,
            used_bytes=1_500_000_000,
            available_bytes=2_500_000_000,
            cached_bytes=800_000_000,
            swap_total_bytes=0,
            swap_used_bytes=0,
        )

    def disks(self) -> DiskUsage:
        return DiskUsage(
            mounts=[
                MountUsage(
                    mountpoint="/",
                    device="/dev/vda1",
                    fstype="ext4",
                    total_bytes=50_000_000_000,
                    used_bytes=20_000_000_000,
                    free_bytes=30_000_000_000,
                    percent=40.0,
                    inodes_total=3_000_000,
                    inodes_used=300_000,
                )
            ]
        )

    def processes(self, sort_by: ProcessSort, limit: int) -> list[ProcessInfo]:
        self.process_calls.append((sort_by, limit))
        return [
            ProcessInfo(
                pid=100 + index,
                name=name,
                user="demo",
                cpu_percent=float(10 - index),
                rss_bytes=1_000_000 * (10 - index),
                started_at="2026-10-13T09:00:00+00:00",
                cmdline=f"/usr/bin/{name} --serve",
            )
            for index, name in enumerate(self.process_names)
        ][:limit]


class FakeJournal:
    def __init__(self, lines: list[LogLine] | None = None) -> None:
        self.lines = lines if lines is not None else [default_log_line()]
        self.calls: list[tuple[str, int, int, JournalPriority]] = []

    def read(
        self, unit: str, since_minutes: int, max_lines: int, min_priority: JournalPriority
    ) -> list[LogLine]:
        self.calls.append((unit, since_minutes, max_lines, min_priority))
        return self.lines[:max_lines]


def default_log_line() -> LogLine:
    return LogLine(
        ts="2026-10-13T09:00:00+00:00", priority=4, message="demo-shop: upstream timeout"
    )


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
    keep_firing_since: datetime | None = None,
) -> PrometheusAlert:
    extra = {} if keep_firing_since is None else {"keepFiringSince": keep_firing_since.isoformat()}
    return PrometheusAlert.model_validate(
        {
            **extra,
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
