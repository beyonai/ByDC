"""Assemble the DataCloud analysis StateGraph (shared by ``agent.create_agent``).

Kept separate from ``agent.py`` so the graph wiring does not create import cycles
with node modules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from datacloud_analysis.orchestration.agent_delegate import agent_delegate_node
from datacloud_analysis.orchestration.clarification import clarification_node
from datacloud_analysis.orchestration.dag import dag_node
from datacloud_analysis.orchestration.direct_tool import direct_tool_node
from datacloud_analysis.orchestration.insight import insight_node
from datacloud_analysis.orchestration.intent import intent_node
from datacloud_analysis.orchestration.loop import loop_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _make_route_after_intent(
    default_tools: dict[str, Any] | None,
) -> Callable[[AgentState], str]:
    """Build router with compile-time tool registry (not persisted in checkpoint state)."""

    dt = default_tools or {}

    def route_after_intent(state: AgentState) -> str:
        """Route after intent node.

        Priority:
          ambiguous_terms → clarification
          clarify_needed / chitchat → insight
          agent_delegate → agent_delegate
          online_query + valid tool → direct_tool
          else → dag
        """
        # 有歧义术语 → 先追问
        if state.get("ambiguous_terms"):
            return "clarification"
        if state.get("query_mode") == "chitchat":
            return "insight"
        tools = state.get("dynamic_tools") or dt
        tt = state.get("target_tool")
        if state.get("query_mode") == "agent_delegate":
            if tt and tt in tools and getattr(tools.get(tt), "_is_agent_delegate", False):
                return "agent_delegate"
            logger.warning(
                "route_after_intent: agent_delegate but target_tool=%r not valid, falling back to dag",
                tt,
            )
        if state.get("query_mode") == "online_query":
            if isinstance(tt, str) and tt.strip() and tt.strip() in tools:
                return "direct_tool"
            logger.warning(
                "route_after_intent: online_query but target_tool=%r not found in available tools=%s"
                ", falling back to dag",
                tt,
                sorted(tools.keys()),
            )
        return "dag"

    return route_after_intent


def _make_route_after_clarification(
    default_tools: dict[str, Any] | None,
) -> Callable[[AgentState], str]:
    """Route after clarification."""

    _ = default_tools or {}

    def route_after_clarification(state: AgentState) -> str:
        # 用户跳过后仍有歧义：按设计回 insight 兜底，不继续执行 dag/direct_tool。
        if state.get("ambiguous_terms"):
            return "insight"
        if state.get("query_mode") == "chitchat":
            return "insight"
        return "intent_replan"

    return route_after_clarification


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
) -> StateGraph[AgentState]:
    """Return an uncompiled ``StateGraph`` for the DataCloud pipeline."""
    builder = StateGraph(AgentState)

    async def _intent(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await intent_node(
            state,
            gateway_context=gw_ctx,
            default_prompts=prompts_overwrite,
            default_tools=tools,
        )

    async def _dag(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await dag_node(
            state,
            gateway_context=gw_ctx,
            default_prompts=prompts_overwrite,
            default_tools=tools,
        )

    async def _loop(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await loop_node(state, gateway_context=gw_ctx, default_tools=tools)

    async def _clarification(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await clarification_node(state, gateway_context=gw_ctx)

    async def _intent_replan(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        replan_query = str(state.get("intent") or "").strip()
        return await intent_node(
            state,
            gateway_context=gw_ctx,
            default_prompts=prompts_overwrite,
            default_tools=tools,
            query_override=replan_query if replan_query else None,
        )

    async def _agent_delegate(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await agent_delegate_node(state, config, default_tools=tools)

    async def _direct_tool(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await direct_tool_node(state, gateway_context=gw_ctx, default_tools=tools)

    async def _insight(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await insight_node(state, gateway_context=gw_ctx, default_prompts=prompts_overwrite)

    builder.add_node("intent", _intent)
    builder.add_node("clarification", _clarification)
    builder.add_node("intent_replan", _intent_replan)
    builder.add_node("agent_delegate", _agent_delegate)
    builder.add_node("direct_tool", _direct_tool)
    builder.add_node("dag", _dag)
    builder.add_node("loop", _loop)
    builder.add_node("insight", _insight)

    builder.add_edge(START, "intent")
    builder.add_conditional_edges(
        "intent",
        _make_route_after_intent(tools),
        {
            "clarification": "clarification",
            "insight": "insight",
            "agent_delegate": "agent_delegate",
            "direct_tool": "direct_tool",
            "dag": "dag",
        },
    )
    builder.add_conditional_edges(
        "clarification",
        _make_route_after_clarification(tools),
        {
            "insight": "insight",
            "intent_replan": "intent_replan",
        },
    )
    builder.add_conditional_edges(
        "intent_replan",
        _make_route_after_intent(tools),
        {
            "clarification": "clarification",
            "insight": "insight",
            "agent_delegate": "agent_delegate",
            "direct_tool": "direct_tool",
            "dag": "dag",
        },
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
