import re
import subprocess
from typing import Protocol

from noc_shared.resources import ManagedResource
from noc_shared.tools import ServiceStatus

STATUS_PROPERTIES = (
    "ActiveState",
    "SubState",
    "NRestarts",
    "ExecMainStatus",
    "ActiveEnterTimestamp",
    "MemoryCurrent",
)
SYSTEMCTL_TIMEOUT_SECONDS = 5
TIMEOUT_PROPERTIES = ("TimeoutStartUSec", "TimeoutStopUSec")
TIMESPAN_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(us|ms|s|min|h|d)\b")
TIMESPAN_UNIT_SECONDS = {"us": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0}


class SystemctlRunner(Protocol):
    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]: ...


class SubprocessSystemctl:
    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        argv = ["/usr/bin/systemctl", "show", unit, "--property=" + ",".join(properties)]
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=SYSTEMCTL_TIMEOUT_SECONDS,
            check=True,
        )
        return parse_key_values(completed.stdout)


def parse_key_values(output: str) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in output.splitlines() if "=" in line)
    return {key: value for key, value in pairs}


def optional_int(value: str | None) -> int | None:
    if value is None or not value.strip().lstrip("-").isdigit():
        return None
    return int(value)


def timespan_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if text == "infinity":
        return float("inf")
    parts = TIMESPAN_PART.findall(text)
    if not parts or TIMESPAN_PART.sub("", text).strip():
        return None
    return sum(float(amount) * TIMESPAN_UNIT_SECONDS[unit] for amount, unit in parts)


def read_service_status(resource: ManagedResource, runner: SystemctlRunner) -> ServiceStatus:
    values = runner.show(resource.name, STATUS_PROPERTIES)
    return ServiceStatus(
        resource_id=resource.id,
        unit=resource.name,
        active_state=values.get("ActiveState", "unknown"),
        sub_state=values.get("SubState", "unknown"),
        restarts=optional_int(values.get("NRestarts")),
        exec_main_status=optional_int(values.get("ExecMainStatus")),
        active_since=values.get("ActiveEnterTimestamp") or None,
        memory_bytes=optional_int(values.get("MemoryCurrent")),
    )
