import logging
import subprocess
from collections.abc import Iterator

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from noc_sentinel.config import SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.tools.systemd import SystemctlRunner, optional_int
from noc_shared.resources import ResourceKind

logger = logging.getLogger(__name__)

METRIC_PROPERTIES = ("ActiveState", "MemoryCurrent", "MemoryMax")


class SentinelCollector(Collector):
    def __init__(
        self, config: SentinelConfig, systemctl: SystemctlRunner, chaos_enabled: bool = False
    ) -> None:
        self._config = config
        self._systemctl = systemctl
        self._chaos_enabled = chaos_enabled

    def collect(self) -> Iterator[GaugeMetricFamily]:
        yield GaugeMetricFamily("noc_sentinel_up", "Sentinel is serving", value=1)
        yield GaugeMetricFamily(
            "noc_sentinel_halted",
            "Target-local kill switch file is present",
            value=1 if is_halted(self._config.halt_file) else 0,
        )
        yield from self._service_families()
        yield GaugeMetricFamily(
            "noc_sentinel_chaos_enabled",
            "Lab-only chaos endpoints are mounted on this target",
            value=1 if self._chaos_enabled else 0,
        )

    def _service_families(self) -> Iterator[GaugeMetricFamily]:
        up = GaugeMetricFamily(
            "noc_service_up", "Registered systemd unit is active", labels=["resource"]
        )
        memory = GaugeMetricFamily(
            "noc_service_memory_bytes",
            "Memory the registered unit's cgroup uses now",
            labels=["resource"],
        )
        memory_max = GaugeMetricFamily(
            "noc_service_memory_max_bytes",
            "MemoryMax limit of the registered unit, when one is set",
            labels=["resource"],
        )
        for resource in self._config.resources_of_kind(ResourceKind.SYSTEMD_UNIT):
            try:
                values = self._systemctl.show(resource.name, METRIC_PROPERTIES)
            except (subprocess.SubprocessError, OSError):
                logger.warning("status read failed for %s", resource.id)
                continue
            up.add_metric([resource.id], 1 if values.get("ActiveState") == "active" else 0)
            used = optional_int(values.get("MemoryCurrent"))
            if used is not None:
                memory.add_metric([resource.id], used)
            limit = optional_int(values.get("MemoryMax"))
            if limit is not None:
                memory_max.add_metric([resource.id], limit)
        yield up
        yield memory
        yield memory_max
