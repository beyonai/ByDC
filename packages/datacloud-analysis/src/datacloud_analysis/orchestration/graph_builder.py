"""Assemble the DataCloud analysis StateGraph.

Main chain (5-node architecture):
knowledge_enhance -> planning -> execution -> end
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from datacloud_analysis.orchestration.end import insight_node
from datacloud_analysis.orchestration.execution import execution_node
from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.planning import planning_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_execution(state: AgentState) -> str:
    status = str(state.get("execution_status") or "done")
    if status == "replan":
        return "planning"
    if status == "execution":
        return "execution"
    return "end"


def build_analysis_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> StateGraph[AgentState]:
    """Return an uncompiled ``StateGraph`` for the DataCloud 5-node pipeline."""
    builder = StateGraph(AgentState)

    async def _knowledge_enhance(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await knowledge_enhance_node(state, gateway_context=gw_ctx)

    async def _planning(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await planning_node(
            state,
            gateway_context=gw_ctx,
            default_prompts=prompts_overwrite,
            default_tools=tools,
        )

    async def _execution(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        return await execution_node(state, config, default_tools=tools)

    async def _end(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        gw_ctx = (config.get("configurable") or {}).get("gateway_context")
        return await insight_node(state, gateway_context=gw_ctx, default_prompts=prompts_overwrite)

    builder.add_node("knowledge_enhance", _knowledge_enhance)
    builder.add_node("planning", _planning)
    builder.add_node("execution", _execution)
    builder.add_node("end", _end)

    builder.add_edge(START, "knowledge_enhance")
    builder.add_edge("knowledge_enhance", "planning")
    builder.add_edge("planning", "execution")
    builder.add_conditional_edges(
        "execution",
        _route_after_execution,
        {
            "planning": "planning",
            "execution": "execution",
            "end": "end",
        },
    )
    builder.add_edge("end", END)

    tool_keys = sorted((tools or {}).keys())
    prompt_keys = sorted((prompts_overwrite or {}).keys())
    logger.info(
        "build_analysis_graph: closure wired — planning/execution receive default_tools "
        "count=%d keys=%s prompts_overwrite_keys=%s",
        len(tool_keys),
        tool_keys,
        prompt_keys,
    )

    return builder
