import pytest
from sqlalchemy import select

from noc.db.models import LlmCall
from noc.db.session import SessionFactory
from noc.llm.client import ProviderRequestRejected
from noc.llm.recording import RecordingLLM
from noc.llm.types import CallContext, ChatMessage, LLMRequest, LLMResponse, Role

pytestmark = pytest.mark.integration

LEAKY_PROVIDER_TEXT = "Incorrect API key provided: gsk_live_ABCD1234"


class FakeStatusError(Exception):
    status_code = 400


class RejectingLLM:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            raise FakeStatusError(LEAKY_PROVIDER_TEXT)
        except FakeStatusError as cause:
            raise ProviderRequestRejected(
                f"groq: request rejected (400): {LEAKY_PROVIDER_TEXT}"
            ) from cause


async def test_a_failed_call_is_recorded_without_the_provider_text(
    sessions: SessionFactory,
) -> None:
    request = LLMRequest(
        tier="small",
        messages=[ChatMessage(role=Role.USER, content="hi")],
        context=CallContext(agent="metrics"),
    )
    with pytest.raises(ProviderRequestRejected):
        await RecordingLLM(RejectingLLM(), sessions).complete(request)
    async with sessions() as session:
        row = await session.scalar(select(LlmCall))
    assert row is not None
    assert row.error == (
        "ProviderRequestRejected (HTTP 400): groq: request rejected (400): "
        "Incorrect API key provided: [key]"
    )
    assert "gsk_" not in (row.error or "")
