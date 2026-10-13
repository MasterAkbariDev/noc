from noc.agents.loop import SKIPPED_TOOL_CALL, AgentLimits, run_tool_agent
from noc.agents.schemas import InvestigationReport
from noc.llm.fake import ScriptedLLM, answer, call_tools
from noc.llm.types import CallContext, Role
from noc.tools.recorder import MemoryToolCallRecorder
from noc.tools.registry import ToolRegistry
from tests.support.builders import investigation_payload, tool_context
from tests.unit.test_tool_registry import spec

STATUS_CALL = ("get_service_status", {"resource_id": "svc:demo-shop"})


async def run(llm: ScriptedLLM, limits: AgentLimits):
    return await run_tool_agent(
        llm,
        ToolRegistry([spec()], MemoryToolCallRecorder()),
        tier="strong",
        system_prompt="system",
        user_prompt="brief",
        output_model=InvestigationReport,
        tool_context=tool_context(),
        call_context=CallContext(agent="investigator"),
        limits=limits,
    )


async def test_agent_calls_tools_then_returns_typed_output() -> None:
    llm = ScriptedLLM([call_tools(STATUS_CALL), answer("done"), answer(investigation_payload())])
    result = await run(llm, AgentLimits(max_rounds=3, max_tool_calls=4))
    assert result.output.diagnosis.primary().root_cause_code == "service_crashed"
    assert set(result.tool_results) == {"T1"}
    assert result.stats.tool_calls == 1
    assert result.stats.llm_calls == 3
    final_request = llm.requests[-1]
    assert final_request.tool_choice == "none"
    assert final_request.response_schema is not None


async def test_round_limit_forces_a_final_answer() -> None:
    llm = ScriptedLLM(
        [call_tools(STATUS_CALL), call_tools(STATUS_CALL), answer(investigation_payload())]
    )
    result = await run(llm, AgentLimits(max_rounds=2, max_tool_calls=8))
    assert result.stats.rounds == 2
    assert result.stats.tool_calls == 2


async def test_tool_budget_skips_extra_calls() -> None:
    llm = ScriptedLLM(
        [call_tools(STATUS_CALL, STATUS_CALL, STATUS_CALL), answer(investigation_payload())]
    )
    result = await run(llm, AgentLimits(max_rounds=1, max_tool_calls=2))
    tool_messages = [m for m in llm.requests[-1].messages if m.role is Role.TOOL]
    assert result.stats.tool_calls == 2
    assert tool_messages[-1].content == SKIPPED_TOOL_CALL
