import httpx2
import pytest
from openai import AsyncOpenAI

from noc.llm.client import ProviderRateLimited, ProviderUnavailable
from noc.llm.openai_compat import OpenAICompatProvider, build_arguments
from noc.llm.types import (
    CallContext,
    ChatMessage,
    LLMRequest,
    LlmToolCall,
    ResponseSchema,
    Role,
    ToolSchema,
)

BASE_URL = "https://llm.test/v1"
TOOL = ToolSchema(name="get_service_status", description="d", parameters={"type": "object"})


def request(**changes: object) -> LLMRequest:
    base = LLMRequest(
        tier="small",
        messages=[
            ChatMessage(role=Role.USER, content="hi"),
            ChatMessage(
                role=Role.ASSISTANT,
                tool_calls=[LlmToolCall(id="c1", name="get_service_status", arguments="{}")],
            ),
            ChatMessage(role=Role.TOOL, tool_call_id="c1", content="result"),
        ],
        context=CallContext(agent="t"),
    )
    return base.model_copy(update=changes)


def test_tools_and_tool_messages_are_mapped() -> None:
    arguments = build_arguments(request(tools=[TOOL]), "m")
    assert arguments["tools"][0]["function"]["name"] == "get_service_status"
    assert arguments["messages"][1]["tool_calls"][0]["id"] == "c1"
    assert arguments["messages"][2]["tool_call_id"] == "c1"
    assert "response_format" not in arguments


def test_schema_is_sent_only_without_tools() -> None:
    schema = ResponseSchema(name="X", json_schema={"type": "object"})
    arguments = build_arguments(request(response_schema=schema), "m")
    assert arguments["response_format"]["json_schema"]["name"] == "X"


def provider_answering(status: int, payload: dict[str, object]) -> OpenAICompatProvider:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx2.Response(status, json=payload)

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    client = AsyncOpenAI(base_url=BASE_URL, api_key="k", max_retries=0, http_client=http_client)
    return OpenAICompatProvider("p", client)


@pytest.mark.parametrize(
    ("status", "error"), [(429, ProviderRateLimited), (503, ProviderUnavailable)]
)
async def test_provider_errors_are_classified(status: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        await provider_answering(status, {}).complete(request(), "m")


async def test_completion_is_parsed() -> None:
    provider = provider_answering(
        200,
        {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c9",
                                "type": "function",
                                "function": {"name": "get_service_status", "arguments": "{}"},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
        },
    )
    response = await provider.complete(request(tools=[TOOL]), "m")
    assert response.tool_calls[0].id == "c9"
    assert response.usage.tokens_in == 11
