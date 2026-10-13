import json
import ssl
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from noc.tools.spec import TargetRef
from noc_shared.actions import ActionRequest, ActionResult
from noc_shared.resources import Inventory
from noc_shared.signing import sign_request
from noc_shared.tools import ToolCallRequest, ToolCallResponse


class SentinelError(Exception):
    pass


class SentinelUnreachable(SentinelError):
    pass


class SentinelRejected(SentinelError):
    pass


ActionReplyKind = Literal["result", "not_found", "unknown"]
ACTION_REFUSAL_STATUSES = frozenset({403, 409, 422, 429})


@dataclass(frozen=True)
class ActionReply:
    kind: ActionReplyKind
    result: ActionResult | None = None
    detail: str = ""


class SentinelClient:
    def __init__(self, base_url: str, key_id: str, secret: bytes, http: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._key_id = key_id
        self._secret = secret
        self._http = http

    async def call_tool(
        self, tool: str, args: dict[str, Any], incident_id: str | None, traceparent: str | None
    ) -> ToolCallResponse:
        body = ToolCallRequest(args=args, incident_id=incident_id).model_dump_json().encode()
        payload = await self._send("POST", f"/v1/tools/{tool}", body, traceparent)
        return ToolCallResponse.model_validate(payload)

    async def run_action(self, action_type: str, request: ActionRequest) -> ActionReply:
        body = request.model_dump_json().encode()
        return await self._action_call("POST", f"/v1/actions/{action_type}", body)

    async def get_action(self, action_id: uuid.UUID) -> ActionReply:
        return await self._action_call("GET", f"/v1/actions/{action_id}", b"")

    async def _action_call(self, method: str, path: str, body: bytes) -> ActionReply:
        url = self._base_url + path
        signed = sign_request(self._key_id, self._secret, method, urlsplit(url).path, body)
        headers = {**signed.as_dict(), "Content-Type": "application/json"}
        try:
            response = await self._http.request(method, url, content=body, headers=headers)
        except httpx.TransportError as exc:
            return ActionReply("unknown", detail=f"{type(exc).__name__}: {exc}"[:300])
        if response.status_code == 200 or response.status_code in ACTION_REFUSAL_STATUSES:
            try:
                return ActionReply("result", ActionResult.model_validate_json(response.content))
            except ValueError:
                return ActionReply("unknown", detail=f"HTTP {response.status_code}: bad body")
        if response.status_code == 404:
            return ActionReply("not_found", detail=response.text[:200])
        return ActionReply("unknown", detail=f"HTTP {response.status_code}: {response.text[:200]}")

    async def inventory(self) -> Inventory:
        return Inventory.model_validate(await self._send("GET", "/v1/inventory", b"", None))

    async def _send(
        self, method: str, path: str, body: bytes, traceparent: str | None
    ) -> dict[str, Any]:
        url = self._base_url + path
        signed = sign_request(self._key_id, self._secret, method, urlsplit(url).path, body)
        headers = {**signed.as_dict(), "Content-Type": "application/json"}
        if traceparent:
            headers["traceparent"] = traceparent
        try:
            response = await self._http.request(method, url, content=body, headers=headers)
        except httpx.TransportError as exc:
            raise SentinelUnreachable(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code >= 400:
            raise SentinelRejected(f"HTTP {response.status_code}: {response.text[:200]}")
        parsed: dict[str, Any] = json.loads(response.content)
        return parsed


class SentinelDirectory:
    def __init__(self, key_dir: Path, http: httpx.AsyncClient) -> None:
        self._key_dir = key_dir
        self._http = http
        self._secrets: dict[str, bytes] = {}

    def _secret(self, key_id: str) -> bytes:
        if key_id not in self._secrets:
            self._secrets[key_id] = (self._key_dir / f"{key_id}.key").read_bytes().strip()
        return self._secrets[key_id]

    def client_for(self, target: TargetRef) -> SentinelClient:
        return SentinelClient(
            target.sentinel_url, target.hmac_key_id, self._secret(target.hmac_key_id), self._http
        )


def build_sentinel_http(
    ca_file: Path | None,
    client_cert: Path | None,
    client_key: Path | None,
    timeout_seconds: float,
) -> httpx.AsyncClient:
    verify: ssl.SSLContext | bool = True
    if ca_file is not None:
        context = ssl.create_default_context(cafile=str(ca_file))
        if client_cert is not None and client_key is not None:
            context.load_cert_chain(str(client_cert), str(client_key))
        verify = context
    return httpx.AsyncClient(verify=verify, timeout=timeout_seconds)
