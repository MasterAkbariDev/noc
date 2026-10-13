import hashlib
import json
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field


class PrometheusAlert(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    state: str
    active_at: datetime = Field(alias="activeAt")
    value: str | None = None

    @property
    def alertname(self) -> str:
        return self.labels.get("alertname", "unknown")

    @property
    def fingerprint(self) -> str:
        return alert_fingerprint(self.labels)


class AlertsPayload(BaseModel):
    alerts: list[PrometheusAlert]


class AlertsResponse(BaseModel):
    status: str
    data: AlertsPayload


class PrometheusUnavailable(Exception):
    pass


def alert_fingerprint(labels: dict[str, str]) -> str:
    canonical = json.dumps(labels, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class PrometheusAlertSource:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._url = base_url.rstrip("/") + "/api/v1/alerts"

    async def firing_alerts(self) -> list[PrometheusAlert]:
        try:
            response = await self._http.get(self._url, timeout=5.0)
            response.raise_for_status()
            parsed = AlertsResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise PrometheusUnavailable(str(exc)) from exc
        if parsed.status != "success":
            raise PrometheusUnavailable(parsed.status)
        return [alert for alert in parsed.data.alerts if alert.state == "firing"]
