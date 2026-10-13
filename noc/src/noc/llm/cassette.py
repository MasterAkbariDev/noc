import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from noc.llm.client import CassetteMiss, LLMClient
from noc.llm.types import LLMRequest, LLMResponse

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
HEX_TRACE_PATTERN = re.compile(r"\b[0-9a-f]{32}\b")

CassetteMode = Literal["record", "replay"]


def normalize_for_key(request: LLMRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"context": {"incident_id"}})
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    for pattern, placeholder in (
        (UUID_PATTERN, "<uuid>"),
        (HEX_TRACE_PATTERN, "<hex>"),
        (TIMESTAMP_PATTERN, "<ts>"),
    ):
        serialized = pattern.sub(placeholder, serialized)
    return serialized


def request_key(request: LLMRequest) -> str:
    return hashlib.sha256(normalize_for_key(request).encode()).hexdigest()


class CassetteLLM:
    def __init__(self, path: Path, mode: CassetteMode, inner: LLMClient | None = None) -> None:
        if mode == "record" and inner is None:
            raise ValueError("record mode needs a live client")
        self._path = path
        self._mode = mode
        self._inner = inner
        self._entries = self._load()

    def _load(self) -> dict[str, LLMResponse]:
        if not self._path.exists():
            return {}
        entries: dict[str, LLMResponse] = {}
        for line in self._path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                entries[record["key"]] = LLMResponse.model_validate(record["response"])
        return entries

    async def complete(self, request: LLMRequest) -> LLMResponse:
        key = request_key(request)
        if self._mode == "replay":
            if key not in self._entries:
                raise CassetteMiss(f"no recorded response for {request.context.agent} ({key[:12]})")
            replayed = self._entries[key].model_copy(deep=True)
            replayed.mode = "replay"
            return replayed

        if self._inner is None:
            raise CassetteMiss("record mode without a live client")
        response = await self._inner.complete(request)
        self._entries[key] = response
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as handle:
            record = {"key": key, "agent": request.context.agent, "response": response.model_dump()}
            handle.write(json.dumps(record) + "\n")
        return response
