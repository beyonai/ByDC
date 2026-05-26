from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.intend.command_router import CommandRouter
from datacloud_analysis.orchestration.message_util import last_human_text
from datacloud_analysis.orchestration.state import AgentState

_router = CommandRouter()
logger = logging.getLogger(__name__)


def _message_line_preview(msg: Any, *, max_len: int = 100) -> str:
    cls = type(msg).__name__
    raw = getattr(msg, "content", "")
    one = raw.replace("\n", "\\n") if isinstance(raw, str) else repr(raw)
    if len(one) > max_len:
        one = one[: max_len - 3] + "..."
    return f"{cls}({one})"


async def intend_node(
    state: AgentState,
    config: RunnableConfig,
) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    messages = state.get("messages") or []
    user_query = last_human_text(messages)

    # target_tool 短路：跳过 LLM，直接构造 tool_call 走 tool_dispatcher
    target_tool = str(state.get("target_tool") or "").strip()
    if target_tool:
        logger.info("[intend_node] target_tool=%r → bypassing LLM, injecting tool_call", target_tool)
        tool_call_id = f"tc_{uuid.uuid4().hex[:12]}"
        ai_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": tool_call_id,
                "name": target_tool,
                "args": {"query": user_query},
                "type": "tool_call",
            }],
        )
        return {
            "intent": "react",
            "intent_source": "target_tool",
            "execution_status": "target_tool_direct",
            "user_query": user_query,
            "messages": [ai_msg],
            "react_round_idx": 1,
        }

    # 1. 命令路由
    result = await _router.try_dispatch(
        user_query=user_query,
        state=state,
        config=config,
        gateway_context=gw_ctx,
    )
    if result["handled"]:
        return {
            "intent": "command",
            "intent_source": "command",
            "command_result": result["payload"],
            "execution_status": "command_done",
            "user_query": user_query,
        }

    return {
        "intent": "react",
        "intent_source": "react",
        "execution_status": "execution",
        "user_query": user_query,
    }
