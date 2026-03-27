"""Assemble the DataCloud analysis StateGraph (shared by ``agent.create_agent``).

Kept separate from ``agent.py`` so the graph wiring does not create import cycles
with node modules.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from datacloud_analysis.orchestration.dag import dag_node
from datacloud_analysis.orchestration.direct_tool import direct_tool_node
from datacloud_analysis.orchestration.insight import insight_node
from datacloud_analysis.orchestration.intent import intent_node
from datacloud_analysis.orchestration.loop import loop_node
from datacloud_analysis.orchestration.state import AgentState


def route_after_intent(state: AgentState) -> str:
    """Route after intent: clarify → insight; online_query+valid tool → direct_tool; else dag."""
    if state.get("clarify_needed"):
        return "insight"
    if state.get("query_mode") == "online_query":
        tools = state.get("dynamic_tools") or {}
        tt = state.get("target_tool")
        if isinstance(tt, str) and tt.strip() and tt.strip() in tools:
            return "direct_tool"
        # LLM 输出了 online_query 但 target_tool 不在可用工具列表中，降级到 dag
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

    async def _direct_tool(state: AgentState) -> dict[str, Any]:
        return await direct_tool_node(state, default_tools=tools)

    async def _insight(state: AgentState) -> dict[str, Any]:
        return await insight_node(state, default_prompts=prompts_overwrite)

    builder.add_node(
        "intent",
        _intent,
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
        {"insight": "insight", "direct_tool": "direct_tool", "dag": "dag"},
    )
    builder.add_edge("direct_tool", "insight")
    builder.add_edge("dag", "loop")
    builder.add_conditional_edges(
        "loop",
        route_loop,
        {"insight": "insight", "loop": "loop"},
    )
    builder.add_edge("insight", END)

    return builder
