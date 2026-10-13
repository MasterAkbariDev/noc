import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from noc.agents.brief import IncidentBrief, render_brief
from noc.agents.grounding import ground_hypothesis
from noc.agents.loop import AgentStats
from noc.agents.schemas import Diagnosis, EvidenceRef, unknown_diagnosis
from noc.llm.client import LLMClient
from noc.llm.structured import complete_structured
from noc.llm.types import CallContext, ChatMessage, LLMRequest, Role, Tier
from noc.tools.sanitize import neutralize
from noc.tools.spec import ToolContext

PROMPT_PATH = Path(__file__).parent / "prompts" / "diagnosis.md"
DIAGNOSIS_AGENT = "diagnosis"
DIAGNOSIS_TIER: Tier = "strong"
UNSUPPORTED = "No hypothesis is supported by grounded findings."


class FindingView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    category: str
    severity: str
    summary: str
    evidence: list[EvidenceRef]
    evidence_strength: str
    counter_evidence: list[str]
    confidence: float
    suspected_injection: bool


@dataclass(frozen=True)
class DiagnosisOutcome:
    diagnosis: Diagnosis
    stats: AgentStats


def render_findings(findings: list[FindingView]) -> str:
    body = neutralize(
        json.dumps([f.model_dump(mode="json") for f in findings], indent=1, sort_keys=True)
    )
    return f'<untrusted_data source="findings">\n{body}\n</untrusted_data>'


def ground_diagnosis(diagnosis: Diagnosis, finding_ids: set[str]) -> Diagnosis:
    hypotheses = [
        kept
        for hypothesis in diagnosis.hypotheses
        if (kept := ground_hypothesis(hypothesis, finding_ids)) is not None
    ]
    if not hypotheses:
        return unknown_diagnosis(UNSUPPORTED)
    return diagnosis.model_copy(update={"hypotheses": hypotheses})


class DiagnosisAgent:
    name = DIAGNOSIS_AGENT

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self._system_prompt = PROMPT_PATH.read_text()

    async def diagnose(
        self, brief: IncidentBrief, findings: list[FindingView], context: ToolContext
    ) -> DiagnosisOutcome:
        user_prompt = f"{render_brief(brief)}\n{render_findings(findings)}"
        request = LLMRequest(
            tier=DIAGNOSIS_TIER,
            messages=[
                ChatMessage(role=Role.SYSTEM, content=self._system_prompt),
                ChatMessage(role=Role.USER, content=user_prompt),
            ],
            context=CallContext(
                agent=self.name,
                incident_id=str(context.incident_id),
                data_policy=context.target.data_policy,
            ),
        )
        final = await complete_structured(self._llm, request, Diagnosis)
        diagnosis = ground_diagnosis(final.value, {finding.label for finding in findings})
        stats = AgentStats(rounds=1, llm_calls=len(final.responses))
        return DiagnosisOutcome(diagnosis, stats)
