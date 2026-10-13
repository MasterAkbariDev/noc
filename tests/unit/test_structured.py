import pytest
from pydantic import BaseModel

from noc.llm.client import StructuredOutputError
from noc.llm.fake import ScriptedLLM, answer
from noc.llm.structured import complete_structured, extract_json
from noc.llm.types import CallContext, ChatMessage, LLMRequest, Role


class Verdict(BaseModel):
    code: str
    confidence: float


REQUEST = LLMRequest(
    tier="small",
    messages=[ChatMessage(role=Role.USER, content="decide")],
    context=CallContext(agent="test"),
)


def test_json_is_extracted_from_fenced_output() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


async def test_valid_output_needs_one_call() -> None:
    llm = ScriptedLLM([answer({"code": "x", "confidence": 0.5})])
    result = await complete_structured(llm, REQUEST, Verdict)
    assert result.value == Verdict(code="x", confidence=0.5)
    assert len(result.responses) == 1


async def test_invalid_output_is_repaired_once() -> None:
    llm = ScriptedLLM([answer("not json"), answer({"code": "x", "confidence": 1.0})])
    result = await complete_structured(llm, REQUEST, Verdict)
    assert result.value.code == "x"
    repair_prompt = llm.requests[1].messages[-1].content or ""
    assert "not valid" in repair_prompt


async def test_repeated_invalid_output_raises() -> None:
    llm = ScriptedLLM([answer("{}"), answer("{}")])
    with pytest.raises(StructuredOutputError):
        await complete_structured(llm, REQUEST, Verdict)
