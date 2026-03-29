"""Agent delegation node — routes the full task to a sub-agent via context.call_agent."""

from __future__ import annotations

import logging
from typing import Any

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def agent_delegate_node(
    state: AgentState,
    config: RunnableConfig,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call an AGENT delegate tool, passing the gateway context for cross-process dispatch.

    Preconditions: router only lands here when target_tool is an _is_agent_delegate tool.
    The tool itself handles streaming via context.emit_chunk / context.call_agent,
    so this node goes directly to END (bypasses insight).
    """
    target_tool = (state.get("target_tool") or "").strip()
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    intent_text = str(state.get("intent") or "")
    gateway_context = (config or {}).get("configurable", {}).get("gateway_context")

    tool_fn = dynamic_tools.get(target_tool)
    if not tool_fn or not getattr(tool_fn, "_is_agent_delegate", False):
        logger.warning(
            "agent_delegate_node: target_tool=%r not found or not an agent delegate tool",
            target_tool,
        )
        return {"plan": [], "results": []}

    logger.info(
        "agent_delegate_node: delegating to agent tool=%s intent=%.100s",
        target_tool,
        intent_text,
    )

    # 关闭思考面板，后续内容作为 ANSWER_DELTA 推送给前端
    if gateway_context is not None:
        await gateway_context.emit_chunk(
            StreamChunkEvent(content="思考完成"),
            event_type=EventType.REASONING_LOG_END.value,
            content_type=SseReasonMessageType.think_title.value,
        )

    try:
        result = await tool_fn(content=intent_text, _context=gateway_context)
        task = {
            "id": "t_agent_delegate",
            "type": target_tool,
            "status": "done",
            "description": intent_text,
        }
        return {
            "plan": [task],
            "results": [{"task_id": "t_agent_delegate", "data": result}],
        }
    except Exception as exc:
        logger.error("agent_delegate_node: tool=%s failed: %s", target_tool, exc)
        task = {
            "id": "t_agent_delegate",
            "type": target_tool,
            "status": "failed",
            "error": str(exc),
        }
        return {"plan": [task], "results": []}
