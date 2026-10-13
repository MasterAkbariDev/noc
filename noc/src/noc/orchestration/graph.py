import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from noc.orchestration.nodes import IncidentNodes, route_after_begin
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState

IncidentGraph = CompiledStateGraph[IncidentState, None, IncidentState, IncidentState]


def build_incident_graph(runtime: Runtime, checkpointer: BaseCheckpointSaver[Any]) -> IncidentGraph:
    nodes = IncidentNodes(runtime)
    graph = StateGraph(IncidentState)
    graph.add_node("begin", nodes.begin)
    graph.add_node("investigate", nodes.investigate)
    graph.add_node("decide", nodes.decide)
    graph.add_node("report", nodes.report)
    graph.add_edge(START, "begin")
    graph.add_conditional_edges(
        "begin", route_after_begin, {"investigate": "investigate", "report": "report"}
    )
    graph.add_edge("investigate", "decide")
    graph.add_edge("decide", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


def thread_config(incident_id: uuid.UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(incident_id)}}


async def run_incident(graph: IncidentGraph, incident_id: uuid.UUID) -> dict[str, Any]:
    config = thread_config(incident_id)
    snapshot = await graph.aget_state(config)
    if snapshot.values and not snapshot.next:
        return dict(snapshot.values)
    initial = None if snapshot.next else IncidentState(incident_id=str(incident_id), outcome=None)
    result = await graph.ainvoke(initial, config)
    return dict(result)
