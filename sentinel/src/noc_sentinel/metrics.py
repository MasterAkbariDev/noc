import logging
import subprocess
from collections.abc import Iterator

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from noc_sentinel.config import SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.tools.systemd import SystemctlRunner, read_service_status
from noc_shared.resources import ResourceKind

logger = logging.getLogger(__name__)


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
        yield self._service_up()
        yield GaugeMetricFamily(
            "noc_sentinel_chaos_enabled",
            "Lab-only chaos endpoints are mounted on this target",
            value=1 if self._chaos_enabled else 0,
        )

    def _service_up(self) -> GaugeMetricFamily:
        family = GaugeMetricFamily(
            "noc_service_up", "Registered systemd unit is active", labels=["resource"]
        )
        for resource in self._config.resources_of_kind(ResourceKind.SYSTEMD_UNIT):
            try:
                status = read_service_status(resource, self._systemctl)
            except (subprocess.SubprocessError, OSError):
                logger.warning("status read failed for %s", resource.id)
                continue
            family.add_metric([resource.id], 1 if status.active_state == "active" else 0)
        return family
