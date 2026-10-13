from dataclasses import dataclass
from pathlib import Path

from noc.agents.brief import IncidentBrief, render_brief
from noc.agents.grounding import GroundedReport, ground_report
from noc.agents.loop import AgentLimits, AgentStats, run_tool_agent
from noc.agents.schemas import InvestigationReport
from noc.llm.client import LLMClient
from noc.llm.types import CallContext, Tier
from noc.tools.catalog import INVESTIGATOR
from noc.tools.registry import ToolRegistry
from noc.tools.spec import ToolContext

PROMPT_PATH = Path(__file__).parent / "prompts" / "investigator.md"
INVESTIGATOR_TIER: Tier = "strong"


@dataclass(frozen=True)
class InvestigationOutcome:
    grounded: GroundedReport
    stats: AgentStats


class SingleInvestigator:
    name = INVESTIGATOR

    def __init__(self, llm: LLMClient, registry: ToolRegistry, limits: AgentLimits) -> None:
        self._llm = llm
        self._registry = registry
        self._limits = limits
        self._system_prompt = PROMPT_PATH.read_text()

    async def investigate(self, brief: IncidentBrief, context: ToolContext) -> InvestigationOutcome:
        result = await run_tool_agent(
            self._llm,
            self._registry,
            tier=INVESTIGATOR_TIER,
            system_prompt=self._system_prompt,
            user_prompt=render_brief(brief),
            output_model=InvestigationReport,
            tool_context=context,
            call_context=CallContext(
                agent=self.name,
                incident_id=str(context.incident_id),
                data_policy=context.target.data_policy,
            ),
            limits=self._limits,
        )
        return InvestigationOutcome(ground_report(result.output, result.tool_results), result.stats)
