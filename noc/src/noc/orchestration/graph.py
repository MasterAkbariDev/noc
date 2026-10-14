import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from noc.orchestration.multi_nodes import DIAGNOSE, SPECIALIST, MultiNodes, route_to_specialists
from noc.orchestration.nodes import (
    IncidentNodes,
    route_after_begin,
    route_after_decide,
    route_after_execute,
)
from noc.orchestration.remediation_nodes import RemediationNodes
from noc.orchestration.runbook_nodes import RunbookNodes
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState

IncidentGraph = CompiledStateGraph[IncidentState, None, IncidentState, IncidentState]
PLAN = "plan"
RUNBOOK_DIAGNOSE = "runbook_diagnose"


def build_incident_graph(runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]) -> IncidentGraph:
    if runtime.settings.agent_mode == "multi":
        return build_multi_graph(runtime, checkpointer)
    return build_single_graph(runtime, checkpointer)


def build_variant_graphs(
    runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]
) -> dict[str, IncidentGraph]:
    return {
        "single": build_single_graph(runtime, checkpointer),
        "multi": build_multi_graph(runtime, checkpointer),
        "multi-strong": build_multi_graph(runtime.with_strong_specialists(), checkpointer),
        "runbook": build_runbook_graph(runtime, checkpointer),
    }


def build_single_graph(runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]) -> IncidentGraph:
    nodes = IncidentNodes(runtime)
    graph = StateGraph(IncidentState)
    graph.add_node("begin", nodes.begin)
    graph.add_node("investigate", nodes.investigate)
    graph.add_node("decide", nodes.decide)
    graph.add_edge(START, "begin")
    graph.add_conditional_edges(
        "begin", route_after_begin, {"investigate": "investigate", "report": "report"}
    )
    graph.add_edge("investigate", "decide")
    add_remediation(graph, RemediationNodes(runtime), nodes)
    return graph.compile(checkpointer=checkpointer)


def build_runbook_graph(runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]) -> IncidentGraph:
    nodes = IncidentNodes(runtime)
    graph = StateGraph(IncidentState)
    graph.add_node("begin", nodes.begin)
    graph.add_node(RUNBOOK_DIAGNOSE, RunbookNodes(runtime).diagnose)
    graph.add_node("decide", nodes.decide)
    graph.add_edge(START, "begin")
    graph.add_conditional_edges(
        "begin", route_after_begin, {"investigate": RUNBOOK_DIAGNOSE, "report": "report"}
    )
    graph.add_edge(RUNBOOK_DIAGNOSE, "decide")
    add_remediation(graph, RemediationNodes(runtime), nodes)
    return graph.compile(checkpointer=checkpointer)


def build_multi_graph(runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]) -> IncidentGraph:
    nodes = MultiNodes(runtime)
    graph = StateGraph(IncidentState)
    graph.add_node("begin", nodes.begin)
    graph.add_node(PLAN, nodes.plan)
    graph.add_node(SPECIALIST, nodes.specialist)
    graph.add_node(DIAGNOSE, nodes.diagnose)
    graph.add_node("decide", nodes.decide)
    graph.add_edge(START, "begin")
    graph.add_conditional_edges(
        "begin", route_after_begin, {"investigate": PLAN, "report": "report"}
    )
    graph.add_conditional_edges(PLAN, route_to_specialists, [SPECIALIST, DIAGNOSE])
    graph.add_edge(SPECIALIST, DIAGNOSE)
    graph.add_edge(DIAGNOSE, "decide")
    add_remediation(graph, RemediationNodes(runtime), nodes)
    return graph.compile(checkpointer=checkpointer)


def add_remediation(
    graph: StateGraph[IncidentState, None, IncidentState, IncidentState],
    remediation: RemediationNodes,
    nodes: IncidentNodes,
) -> None:
    graph.add_node("execute", remediation.execute)
    graph.add_node("verify", remediation.verify)
    graph.add_node("report", nodes.report)
    graph.add_conditional_edges(
        "decide", route_after_decide, {"execute": "execute", "wait": END, "report": "report"}
    )
    graph.add_conditional_edges(
        "execute", route_after_execute, {"verify": "verify", "report": "report"}
    )
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)


def build_remediation_graph(
    runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]
) -> IncidentGraph:
    remediation = RemediationNodes(runtime)
    graph = StateGraph(IncidentState)
    graph.add_node("execute", remediation.execute)
    graph.add_node("verify", remediation.verify)
    graph.add_node("report", IncidentNodes(runtime).report)
    graph.add_edge(START, "execute")
    graph.add_conditional_edges(
        "execute", route_after_execute, {"verify": "verify", "report": "report"}
    )
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


def thread_config(incident_id: uuid.UUID, suffix: str = "") -> RunnableConfig:
    thread = str(incident_id) if not suffix else f"{incident_id}:{suffix}"
    return {"configurable": {"thread_id": thread}}


async def run_incident(
    graph: IncidentGraph, incident_id: uuid.UUID, suffix: str = ""
) -> dict[str, Any]:
    config = thread_config(incident_id, suffix)
    snapshot = await graph.aget_state(config)
    if snapshot.values and not snapshot.next:
        return dict(snapshot.values)
    initial = None if snapshot.next else IncidentState(incident_id=str(incident_id), outcome=None)
    result = await graph.ainvoke(initial, config)
    return dict(result)
