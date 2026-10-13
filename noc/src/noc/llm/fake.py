import json
from collections.abc import Callable
from typing import Any

from noc.llm.types import LLMRequest, LLMResponse, LlmToolCall

ScriptStep = LLMResponse | Callable[[LLMRequest], LLMResponse]


class ScriptedLLM:
    def __init__(self, steps: list[ScriptStep]) -> None:
        self._steps = list(steps)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._steps:
            raise AssertionError("ScriptedLLM ran out of scripted responses")
        step = self._steps.pop(0)
        response = step(request) if callable(step) else step
        return response.model_copy(deep=True)


def answer(payload: dict[str, Any] | str) -> LLMResponse:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMResponse(content=content, provider="fake", model="scripted", finish_reason="stop")


def call_tools(*calls: tuple[str, dict[str, Any]]) -> LLMResponse:
    tool_calls = [
        LlmToolCall(id=f"call_{index}", name=name, arguments=json.dumps(arguments))
        for index, (name, arguments) in enumerate(calls, start=1)
    ]
    return LLMResponse(
        tool_calls=tool_calls, provider="fake", model="scripted", finish_reason="tool_calls"
    )
