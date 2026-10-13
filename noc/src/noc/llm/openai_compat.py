import time
from typing import Any

import openai
from openai import AsyncOpenAI

from noc.llm.client import ProviderRateLimited, ProviderUnavailable
from noc.llm.types import ChatMessage, LLMRequest, LLMResponse, LlmToolCall, Role, Usage


def to_openai_message(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.role is Role.ASSISTANT and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.role is Role.TOOL:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def build_arguments(request: LLMRequest, model: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "model": model,
        "messages": [to_openai_message(message) for message in request.messages],
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


class OpenAICompatProvider:
    def __init__(self, name: str, client: AsyncOpenAI) -> None:
        self.name = name
        self._client = client

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        started = time.monotonic()
        try:
            completion = await self._client.chat.completions.create(
                **build_arguments(request, model)
            )
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(f"{self.name}: {exc}") from exc
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            raise ProviderUnavailable(f"{self.name}: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(f"{self.name}: {exc.status_code}") from exc
            raise

        choice = completion.choices[0]
        tool_calls = [
            LlmToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
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
