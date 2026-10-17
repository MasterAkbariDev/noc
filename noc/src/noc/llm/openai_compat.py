import time
from collections.abc import Mapping
from typing import Any

import openai
from openai import AsyncOpenAI

from noc.llm.client import (
    ProviderBadGeneration,
    ProviderKeyRejected,
    ProviderModelUnavailable,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderUnavailable,
)
from noc.llm.types import ChatMessage, LLMRequest, LLMResponse, LlmToolCall, Role, Usage


def tool_call_extra(
    call: LlmToolCall, provider: str, foreign_extra: dict[str, Any]
) -> dict[str, Any]:
    return call.provider_extra if call.provider == provider else foreign_extra


def to_openai_message(
    message: ChatMessage, provider: str = "", foreign_extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.role is Role.ASSISTANT and message.tool_calls:
        payload["tool_calls"] = [
            {
                **tool_call_extra(call, provider, foreign_extra or {}),
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.role is Role.TOOL:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def build_arguments(
    request: LLMRequest,
    model: str,
    provider: str = "",
    foreign_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages = [to_openai_message(message, provider, foreign_extra) for message in request.messages]
    arguments: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": request.temperature,
    }
    if request.tools:
        arguments["tools"] = [
            {"type": "function", "function": tool.model_dump()} for tool in request.tools
        ]
        arguments["tool_choice"] = request.tool_choice
    elif request.response_schema is not None:
        arguments["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.response_schema.name,
                "schema": request.response_schema.json_schema,
            },
        }
    return arguments


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("retry-after")
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except ValueError:
        return None


INVALID_KEY_MARKERS = ("api key not valid", "invalid api key", "api_key_invalid")
BAD_GENERATION_MARKERS = ("tool_use_failed", "failed to parse tool call")
MODEL_GONE_MARKERS = (
    "decommissioned",
    "no longer available",
    "model_not_found",
    "does not exist",
    "not found for api version",
)


def is_invalid_key_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in INVALID_KEY_MARKERS)


def is_bad_generation_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in BAD_GENERATION_MARKERS)


def is_model_gone_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in MODEL_GONE_MARKERS)


class OpenAICompatProvider:
    def __init__(
        self, name: str, client: AsyncOpenAI, foreign_tool_call_extra: dict[str, Any] | None = None
    ) -> None:
        self.name = name
        self._client = client
        self._foreign_extra = foreign_tool_call_extra or {}

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        started = time.monotonic()
        try:
            completion = await self._client.chat.completions.create(
                **build_arguments(request, model, self.name, self._foreign_extra)
            )
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(
                f"{self.name}: rate limited", retry_after_seconds(exc.response.headers)
            ) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise ProviderKeyRejected(f"{self.name}: key rejected ({exc.status_code})") from exc
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            raise ProviderUnavailable(f"{self.name}: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(f"{self.name}: {exc.status_code}") from exc
            if is_invalid_key_message(str(exc)):
                raise ProviderKeyRejected(f"{self.name}: key rejected ({exc.status_code})") from exc
            if is_bad_generation_message(str(exc)):
                raise ProviderBadGeneration(
                    f"{self.name}: the model wrote a broken tool call"
                ) from exc
            if exc.status_code == 404 or is_model_gone_message(str(exc)):
                raise ProviderModelUnavailable(
                    f"{self.name}: model {model} is not available ({exc.status_code})"
                ) from exc
            raise ProviderRequestRejected(
                f"{self.name}: request rejected ({exc.status_code}): {exc.message[:300]}"
            ) from exc

        choice = completion.choices[0]
        tool_calls = [
            LlmToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments,
                provider=self.name,
                provider_extra=dict(call.model_extra or {}),
            )
            for call in (choice.message.tool_calls or [])
            if call.type == "function"
        ]
        usage = completion.usage
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            provider=self.name,
            model=model,
            usage=Usage(
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
