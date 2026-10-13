from dataclasses import dataclass

import httpx

from noc.agents.investigator import SingleInvestigator
from noc.agents.loop import AgentLimits
from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.client import LLMClient
from noc.llm.factory import build_llm
from noc.policy.loader import PolicyDocument, load_policy
from noc.tools.catalog import build_read_tools
from noc.tools.recorder import DatabaseToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.sentinel_client import SentinelDirectory


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    sessions: SessionFactory
    llm: LLMClient
    registry: ToolRegistry
    policy: PolicyDocument
    investigator: SingleInvestigator


def build_runtime(
    settings: Settings,
    sessions: SessionFactory,
    sentinel_http: httpx.AsyncClient,
    llm: LLMClient | None = None,
) -> Runtime:
    llm_client = llm or build_llm(settings, sessions)
    sentinels = SentinelDirectory(settings.sentinel_key_dir, sentinel_http)
    registry = ToolRegistry(build_read_tools(sentinels), DatabaseToolCallRecorder(sessions))
    limits = AgentLimits(
        max_rounds=settings.investigator_max_rounds,
        max_tool_calls=settings.investigator_max_tool_calls,
    )
    return Runtime(
        settings=settings,
        sessions=sessions,
        llm=llm_client,
        registry=registry,
        policy=load_policy(settings.policy_file),
        investigator=SingleInvestigator(llm_client, registry, limits),
    )
