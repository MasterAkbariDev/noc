import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from noc.llm.client import LLMClient
from noc.llm.structured import complete_structured
from noc.llm.types import CallContext, ChatMessage, LLMRequest, Role, Tier
from noc.tools.registry import ToolRegistry, ToolResult
from noc.tools.spec import ToolContext

FINAL_ANSWER_INSTRUCTION = (
    "Stop calling tools. Return your final answer now as one JSON object that matches this "
    "JSON schema exactly, with no prose around it:\n{schema}"
)
SKIPPED_TOOL_CALL = "Skipped: this agent's tool call budget is used up."


@dataclass
class AgentStats:
    rounds: int = 0
    llm_calls: int = 0
    tool_calls: int = 0


@dataclass
class AgentResult[OutputT: BaseModel]:
    output: OutputT
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    stats: AgentStats = field(default_factory=AgentStats)


@dataclass(frozen=True)
class AgentLimits:
    max_rounds: int = 3
    max_tool_calls: int = 8


async def run_tool_agent[OutputT: BaseModel](
    llm: LLMClient,
    registry: ToolRegistry,
    *,
    tier: Tier,
    system_prompt: str,
    user_prompt: str,
    output_model: type[OutputT],
    tool_context: ToolContext,
    call_context: CallContext,
    limits: AgentLimits,
) -> AgentResult[OutputT]:
    stats = AgentStats()
    results: dict[str, ToolResult] = {}
    messages = [
        ChatMessage(role=Role.SYSTEM, content=system_prompt),
        ChatMessage(role=Role.USER, content=user_prompt),
    ]
    tools = registry.schemas_for(tool_context.agent)

    for _round in range(limits.max_rounds):
        stats.rounds += 1
        response = await llm.complete(
            LLMRequest(tier=tier, messages=messages, tools=tools, context=call_context)
        )
        stats.llm_calls += 1
        messages.append(response.as_assistant_message())
        if not response.tool_calls:
            break
        for call in response.tool_calls:
            if stats.tool_calls >= limits.max_tool_calls:
                content = SKIPPED_TOOL_CALL
            else:
                result = await registry.execute(call.name, call.arguments, tool_context)
                results[result.ref] = result
                stats.tool_calls += 1
                content = result.content
            messages.append(ChatMessage(role=Role.TOOL, tool_call_id=call.id, content=content))

    schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
    messages.append(
        ChatMessage(role=Role.USER, content=FINAL_ANSWER_INSTRUCTION.format(schema=schema))
    )
    final = await complete_structured(
        llm,
        LLMRequest(tier=tier, messages=messages, tools=tools, context=call_context),
        output_model,
    )
    stats.llm_calls += len(final.responses)
    return AgentResult(output=final.value, tool_results=results, stats=stats)
