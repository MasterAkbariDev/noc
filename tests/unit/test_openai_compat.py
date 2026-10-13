import httpx2
import pytest
from openai import AsyncOpenAI

from noc.llm.client import (
    ProviderBadGeneration,
    ProviderKeyRejected,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderUnavailable,
)
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


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (401, {"error": {"message": "Incorrect API key provided"}}),
        (400, {"error": {"message": "API key not valid. Please pass a valid API key."}}),
    ],
)
async def test_bad_keys_are_classified_as_rejected(status: int, payload: dict[str, object]) -> None:
    with pytest.raises(ProviderKeyRejected):
        await provider_answering(status, payload).complete(request(), "m")


async def test_provider_specific_tool_call_fields_are_kept_and_sent_back() -> None:
    signature = {"google": {"thought_signature": "SIG-123"}}
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
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "get_host_overview", "arguments": "{}"},
                                "extra_content": signature,
                            }
                        ],
                    },
                }
            ],
        },
    )
    response = await provider.complete(request(tools=[TOOL]), "m")
    assert response.tool_calls[0].provider_extra == {"extra_content": signature}
    assert response.tool_calls[0].provider == "p"
    history = request(messages=[response.as_assistant_message()], tools=[TOOL])
    sent = build_arguments(history, "m", "p")
    assert sent["messages"][0]["tool_calls"][0]["extra_content"] == signature
    elsewhere = build_arguments(history, "m", "groq")
    assert "extra_content" not in elsewhere["messages"][0]["tool_calls"][0]


def test_tool_calls_from_another_provider_get_the_placeholder_extra() -> None:
    call = LlmToolCall(id="c1", name="get_host_overview", arguments="{}", provider="groq")
    message = ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=[call])
    placeholder = {"extra_content": {"google": {"thought_signature": "skip"}}}
    sent = build_arguments(request(messages=[message], tools=[TOOL]), "m", "gemini", placeholder)
    assert sent["messages"][0]["tool_calls"][0]["extra_content"] == placeholder["extra_content"]


async def test_a_broken_tool_call_from_the_model_is_retryable() -> None:
    payload = {
        "error": {
            "message": "Failed to parse tool call arguments as JSON",
            "code": "tool_use_failed",
        }
    }
    with pytest.raises(ProviderBadGeneration):
        await provider_answering(400, payload).complete(request(), "m")


async def test_other_client_errors_become_llm_errors() -> None:
    payload = {"error": {"message": "Function call is missing a thought_signature"}}
    with pytest.raises(ProviderRequestRejected, match="thought_signature"):
        await provider_answering(400, payload).complete(request(), "m")
