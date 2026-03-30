"""One-shot dynamic tool invocation for online_query fast path (skip dag/loop)."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_analysis.orchestration.sandbox_executor import execute_next_task
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def direct_tool_node(
    state: AgentState,
    gateway_context: Any = None,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a single bound dynamic tool and populate plan/results for insight.

    Preconditions: router only lands here when target_tool exists in dynamic_tools.
    """
    target_tool = (state.get("target_tool") or "").strip()
    raw_params = state.get("tool_params")
    tool_params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    intent_text = str(state.get("intent") or "")

    if not target_tool or target_tool not in dynamic_tools:
        logger.warning(
            "direct_tool_node: missing or unknown target_tool=%r, returning empty plan",
            target_tool,
        )
        return {"plan": [], "results": []}

    task: dict[str, Any] = {
        "id": "t_direct",
        "type": target_tool,
        "status": "pending",
        "deps": [],
        "params": tool_params,
        "description": intent_text,
    }
    updated_task, output = await execute_next_task(
        task,
        state,
        gateway_context=gateway_context,
        custom_tools=dynamic_tools,
    )
    logger.info(
        "direct_tool_node: tool=%s status=%s",
        target_tool,
        updated_task.get("status"),
    )
    return {
        "plan": [updated_task],
        "results": [{"task_id": "t_direct", "data": output}],
    }
