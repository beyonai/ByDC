from __future__ import annotations
import logging
from typing import Any
from langchain_core.runnables import RunnableConfig
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.orchestration.respond.formatter import format_result

logger = logging.getLogger(__name__)

async def respond_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    react_final = state.get("react_final") or {}
    workspace_dir = state.get("workspace_dir")

    if not react_final:
        logger.warning("respond_node: react_final is empty")
        await format_result({"result_type": "text", "answer": ""}, gw_ctx, workspace_dir)
        return {}

    await format_result(react_final, gw_ctx, workspace_dir)
    return {}
