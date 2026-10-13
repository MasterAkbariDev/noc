import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from noc.llm.types import ToolSchema
from noc_shared.permissions import PermissionClass


@dataclass(frozen=True)
class TargetRef:
    id: uuid.UUID
    name: str
    sentinel_url: str
    hmac_key_id: str
    environment: str
    data_policy: str


@dataclass(frozen=True)
class ToolContext:
    incident_id: uuid.UUID
    agent: str
    target: TargetRef
    trace_id: str


@dataclass(frozen=True)
class ToolOutput:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    permission: PermissionClass
    agents: frozenset[str]
    handler: ToolHandler
    untrusted_fields: tuple[str, ...] = ()
    max_result_chars: int = 6_000
    timeout_seconds: float = 15.0
    tags: frozenset[str] = field(default_factory=frozenset)

    def llm_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(),
        )
