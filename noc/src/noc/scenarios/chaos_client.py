import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from noc.config import Settings
from noc.tools.sentinel_client import build_sentinel_http
from noc_shared.resources import ResourceId
from noc_shared.signing import sign_request

CHAOS_PREFIX = "/v1/chaos"
SERVICE_DOWN_START = f"{CHAOS_PREFIX}/service-down/start"
SERVICE_DOWN_STOP = f"{CHAOS_PREFIX}/service-down/stop"
CHAOS_STATUS = f"{CHAOS_PREFIX}/status"
NOT_ACTIVE = "NOT_ACTIVE"


class ChaosError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ChaosState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active: bool
    resource_id: str | None = None
    expires_at: datetime | None = None


class ServiceDownStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    ttl_seconds: int = Field(ge=1)


class ServiceDownStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId


class ChaosClient(Protocol):
    async def status(self) -> ChaosState: ...

    async def start_service_down(self, resource_id: str, ttl_seconds: int) -> ChaosState: ...

    async def stop_service_down(self, resource_id: str) -> ChaosState: ...


class SentinelChaosClient:
    def __init__(self, base_url: str, key_id: str, secret: bytes, http: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._key_id = key_id
        self._secret = secret
        self._http = http

    async def status(self) -> ChaosState:
        return ChaosState.model_validate(await self._send("GET", CHAOS_STATUS, b""))

    async def start_service_down(self, resource_id: str, ttl_seconds: int) -> ChaosState:
        body = ServiceDownStart(resource_id=resource_id, ttl_seconds=ttl_seconds)
        payload = await self._send("POST", SERVICE_DOWN_START, body.model_dump_json().encode())
        return ChaosState.model_validate(payload)

    async def stop_service_down(self, resource_id: str) -> ChaosState:
        body = ServiceDownStop(resource_id=resource_id)
        payload = await self._send("POST", SERVICE_DOWN_STOP, body.model_dump_json().encode())
        return ChaosState.model_validate(payload)

    async def _send(self, method: str, path: str, body: bytes) -> dict[str, Any]:
        url = self._base_url + path
        signed = sign_request(self._key_id, self._secret, method, urlsplit(url).path, body)
        headers = {**signed.as_dict(), "Content-Type": "application/json"}
        try:
            response = await self._http.request(method, url, content=body, headers=headers)
        except httpx.TransportError as exc:
            raise ChaosError("UNREACHABLE") from exc
        if response.status_code >= 400:
            raise ChaosError(error_code(response))
        parsed: dict[str, Any] = json.loads(response.content)
        return parsed


def error_code(response: httpx.Response) -> str:
    fallback = f"HTTP {response.status_code}"
    try:
        body: Any = response.json()
    except ValueError:
        return fallback
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else fallback


def chaos_secret(key_dir: Path, key_id: str) -> bytes:
    return (key_dir / f"{key_id}.key").read_bytes().strip()


def build_chaos_client(sentinel_url: str, settings: Settings) -> SentinelChaosClient:
    if settings.chaos_key_dir is None:
        raise ValueError("NOC_CHAOS_KEY_DIR is not set; chaos key is required for scenarios")
    secret = chaos_secret(settings.chaos_key_dir, settings.chaos_key_id)
    http = build_sentinel_http(
        settings.sentinel_ca_file,
        settings.sentinel_client_cert,
        settings.sentinel_client_key,
        settings.sentinel_timeout_seconds,
    )
    return SentinelChaosClient(sentinel_url, settings.chaos_key_id, secret, http)
