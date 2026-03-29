"""Assemble the DataCloud analysis StateGraph (shared by ``agent.create_agent``).

Kept separate from ``agent.py`` so the graph wiring does not create import cycles
with node modules.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from datacloud_analysis.orchestration.agent_delegate import agent_delegate_node
from datacloud_analysis.orchestration.dag import dag_node
from datacloud_analysis.orchestration.direct_tool import direct_tool_node
from datacloud_analysis.orchestration.insight import insight_node
from datacloud_analysis.orchestration.intent import intent_node
from datacloud_analysis.orchestration.loop import loop_node
from datacloud_analysis.orchestration.state import AgentState


def route_after_intent(state: AgentState) -> str:
    """Route after intent: clarify → insight; agent_delegate → agent_delegate; online_query+valid tool → direct_tool; else dag."""
    if state.get("clarify_needed"):
        return "insight"
    tools = state.get("dynamic_tools") or {}
    tt = (state.get("target_tool") or "").strip()
    if state.get("query_mode") == "agent_delegate":
        if tt and tt in tools and getattr(tools.get(tt), "_is_agent_delegate", False):
            return "agent_delegate"
        logger.warning(
            "route_after_intent: agent_delegate but target_tool=%r not valid, falling back to dag",
            tt,
        )
    if state.get("query_mode") == "online_query":
        if tt and tt in tools:
            return "direct_tool"
        logger.warning(
            "route_after_intent: online_query but target_tool=%r not found in available tools=%s"
            ", falling back to dag",
            tt,
            sorted(tools.keys()),
        )
    return "dag"


def route_loop(state: AgentState) -> str:
    """Route after loop iteration."""
    plan = state.get("plan", [])
    pending = [t for t in plan if t.get("status") == "pending"]
    if not pending:
        return "insight"
    return "loop"


def build_analysis_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> StateGraph:
    """Return an uncompiled ``StateGraph`` for the DataCloud pipeline."""
    builder = StateGraph(AgentState)

    async def _intent(state: AgentState) -> dict[str, Any]:
        return await intent_node(state, default_prompts=prompts_overwrite)

    async def _dag(state: AgentState) -> dict[str, Any]:
        return await dag_node(
            state,
            default_prompts=prompts_overwrite,
            default_tools=tools,
        )

    async def _loop(state: AgentState) -> dict[str, Any]:
        return await loop_node(state, default_tools=tools)

    async def _agent_delegate(state: AgentState) -> dict[str, Any]:
        return await agent_delegate_node(state, default_tools=tools)

    async def _direct_tool(state: AgentState) -> dict[str, Any]:
        return await direct_tool_node(state, default_tools=tools)

    async def _insight(state: AgentState) -> dict[str, Any]:
        return await insight_node(state, default_prompts=prompts_overwrite)

    builder.add_node(
        "intent",
        _intent,
    )
    builder.add_node(
        "agent_delegate",
        _agent_delegate,
    )
    builder.add_node(
        "direct_tool",
        _direct_tool,
    )
    builder.add_node(
        "dag",
        _dag,
    )
    builder.add_node(
        "loop",
        _loop,
    )
    builder.add_node(
        "insight",
        _insight,
    )

    builder.add_edge(START, "intent")
    builder.add_conditional_edges(
        "intent",
        route_after_intent,
        {"insight": "insight", "agent_delegate": "agent_delegate", "direct_tool": "direct_tool", "dag": "dag"},
    )
    builder.add_edge("agent_delegate", END)
    builder.add_edge("direct_tool", "insight")
    builder.add_edge("dag", "loop")
    builder.add_conditional_edges(
        "loop",
        route_loop,
        {"insight": "insight", "loop": "loop"},
    )
    builder.add_edge("insight", END)

    return builder
