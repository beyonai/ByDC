"""Assemble the DataCloud analysis StateGraph.

New 3-node architecture: intend → execution → respond
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from datacloud_analysis.orchestration.execution.node import execution_node
from datacloud_analysis.orchestration.intend.node import intend_node
from datacloud_analysis.orchestration.respond.node import respond_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_intend(state: AgentState) -> str:
    status = str(state.get("execution_status") or "execution")
    if status == "command_done":
        return "command_done"
    return "execution"


def _as_state_update(value: object, *, node_name: str) -> dict[str, Any]:
    """Normalize node output into a concrete state update mapping."""
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    msg = f"{node_name} node must return a mapping, got {type(value).__name__}"
    raise TypeError(msg)


def build_analysis_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    knowledge_enhancer: Callable[..., Any] | None = None,
) -> StateGraph[AgentState]:
    """Return an uncompiled StateGraph for the DataCloud 3-node pipeline."""
    builder = StateGraph(AgentState)

    async def _intend(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await intend_node(state, config, knowledge_enhancer=knowledge_enhancer)
        return _as_state_update(result, node_name="intend")

    async def _execution(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await execution_node(
            state,
            config,
            default_tools=tools,
            prompts_overwrite=prompts_overwrite,
        )
        return _as_state_update(result, node_name="execution")

    async def _respond(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await respond_node(state, config)
        return _as_state_update(result, node_name="respond")

    builder.add_node("intend", _intend)
    builder.add_node("execution", _execution)
    builder.add_node("respond", _respond)

    builder.add_edge(START, "intend")
    builder.add_conditional_edges(
        "intend",
        _route_after_intend,
        {
            "command_done": END,
            "execution": "execution",
        },
    )
    builder.add_edge("execution", "respond")
    builder.add_edge("respond", END)

    tool_keys = sorted((tools or {}).keys())
    logger.info(
        "build_analysis_graph: 3-node pipeline wired — tools count=%d keys=%s knowledge_enhancer=%s",
        len(tool_keys),
        tool_keys,
        knowledge_enhancer is not None,
    )

    return builder
