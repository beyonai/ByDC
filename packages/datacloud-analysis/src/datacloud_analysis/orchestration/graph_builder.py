"""Assemble the DataCloud analysis StateGraph (shared by ``agent.create_agent``).

Kept separate from ``agent.py`` so the graph wiring does not create import cycles
with node modules.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from datacloud_analysis.orchestration.dag import dag_node
from datacloud_analysis.orchestration.insight import insight_node
from datacloud_analysis.orchestration.intent import intent_node
from datacloud_analysis.orchestration.loop import loop_node
from datacloud_analysis.orchestration.state import AgentState


def route_intent(state: AgentState) -> str:
    """Route after intent parsing."""
    if state.get("clarify_needed"):
        return "insight"
    return "dag"


def route_loop(state: AgentState) -> str:
    """Route after loop iteration."""
    plan = state.get("plan", [])
    pending = [t for t in plan if t.get("status") == "pending"]
    if not pending:
        return "insight"
    return "loop"


def build_analysis_graph() -> StateGraph:
    """Return an uncompiled ``StateGraph`` for the DataCloud pipeline."""
    builder = StateGraph(AgentState)

    builder.add_node("intent", intent_node)
    builder.add_node("dag", dag_node)
    builder.add_node("loop", loop_node)
    builder.add_node("insight", insight_node)

    builder.add_edge(START, "intent")
    builder.add_conditional_edges(
        "intent",
        route_intent,
        {"insight": "insight", "dag": "dag"},
    )
    builder.add_edge("dag", "loop")
    builder.add_conditional_edges(
        "loop",
        route_loop,
        {"insight": "insight", "loop": "loop"},
    )
    builder.add_edge("insight", END)

    return builder
