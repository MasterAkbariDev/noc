from dataclasses import dataclass
from pathlib import Path

import httpx

from noc.agents import specialist as specialist_module
from noc.agents.diagnosis import DiagnosisAgent
from noc.agents.investigator import SingleInvestigator
from noc.agents.loop import AgentLimits
from noc.agents.specialist import SpecialistAgent
from noc.agents.supervisor import RoutingTable, Specialist, load_routing
from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.client import LLMClient
from noc.llm.factory import build_llm
from noc.policy.loader import PolicyDocument, load_policy
from noc.tools.catalog import build_metric_tools, build_read_tools
from noc.tools.prometheus_tools import DatabaseResourceLookup, PrometheusClient
from noc.tools.recorder import DatabaseToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.sentinel_client import SentinelDirectory
from noc.tools.spec import ToolSpec

ROUTING_FILE = Path(__file__).parent / "routing.yaml"
SPECIALIST_PROMPTS = Path(specialist_module.__file__).parent / "prompts"
IMPLEMENTED_SPECIALISTS: tuple[Specialist, ...] = ("metrics", "logs", "network", "security")


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    sessions: SessionFactory
    llm: LLMClient
    registry: ToolRegistry
    policy: PolicyDocument
    investigator: SingleInvestigator
    routing: RoutingTable
    specialists: dict[Specialist, SpecialistAgent]
    diagnoser: DiagnosisAgent


def build_runtime(
    settings: Settings,
    sessions: SessionFactory,
    sentinel_http: httpx.AsyncClient,
    llm: LLMClient | None = None,
    prometheus_http: httpx.AsyncClient | None = None,
    prometheus_url: str | None = None,
) -> Runtime:
    llm_client = llm or build_llm(settings, sessions)
    sentinels = SentinelDirectory(settings.sentinel_key_dir, sentinel_http)
    tools: list[ToolSpec] = build_read_tools(sentinels)
    if prometheus_http is not None:
        client = PrometheusClient(prometheus_http, prometheus_url or settings.prometheus_url)
        tools += build_metric_tools(client, DatabaseResourceLookup(sessions))
    registry = ToolRegistry(tools, DatabaseToolCallRecorder(sessions))
    limits = AgentLimits(
        max_rounds=settings.investigator_max_rounds,
        max_tool_calls=settings.investigator_max_tool_calls,
    )
    specialist_limits = AgentLimits(
        max_rounds=settings.specialist_max_rounds,
        max_tool_calls=settings.specialist_max_tool_calls,
    )
    specialists = {
        name: SpecialistAgent(
            llm_client, registry, name, SPECIALIST_PROMPTS / f"{name}.md", specialist_limits
        )
        for name in IMPLEMENTED_SPECIALISTS
    }
    return Runtime(
        settings=settings,
        sessions=sessions,
        llm=llm_client,
        registry=registry,
        policy=load_policy(settings.policy_file),
        investigator=SingleInvestigator(llm_client, registry, limits),
        routing=load_routing(ROUTING_FILE),
        specialists=specialists,
        diagnoser=DiagnosisAgent(llm_client),
    )
