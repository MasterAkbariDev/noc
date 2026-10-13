from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

Tier = Literal["small", "strong"]


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LlmToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class ChatMessage(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[LlmToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ResponseSchema(BaseModel):
    name: str
    json_schema: dict[str, Any]


class CallContext(BaseModel):
    agent: str
    incident_id: str | None = None
    data_policy: str = "redacted"


class LLMRequest(BaseModel):
    tier: Tier
    messages: list[ChatMessage]
    tools: list[ToolSchema] = Field(default_factory=list)
    tool_choice: Literal["auto", "none"] = "auto"
    response_schema: ResponseSchema | None = None
    temperature: float = 0.0
    context: CallContext


class Usage(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[LlmToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    provider: str = "unknown"
    model: str = "unknown"
    usage: Usage = Field(default_factory=Usage)
    latency_ms: int = 0
    wait_ms: int = 0
    fallback: bool = False
    redactions: int = 0
    mode: str = "live"

    def as_assistant_message(self) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, content=self.content, tool_calls=self.tool_calls)
