from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from datacloud_analysis.orchestration.message_util import extract_ai_text
from datacloud_analysis.orchestration.respond.formatter import format_result
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _clear_messages_update() -> dict[str, Any]:
    """Build a LangGraph update that clears accumulated conversation messages."""
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)]}


async def respond_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    react_final = state.get("react_final") or {}
    workspace_dir = state.get("workspace_dir")

    if not react_final:
        # L2/L3 兜底：should_continue 直接路由到 respond 时 react_final 未设置
        messages = list(state.get("messages") or [])
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        answer = extract_ai_text(last_ai.content) if last_ai else ""
        react_final = {
            "result_type": "text",
            "answer": answer,
            "answer_streamed": bool(state.get("answer_streamed")),
        }
        logger.warning(
            "respond_node: react_final is empty, built fallback from AIMessage answer_len=%d",
            len(answer),
        )

    final_answer = await format_result(react_final, gw_ctx, workspace_dir, config=config)
    update = _clear_messages_update()
    if final_answer is not None:
        update["final_answer"] = final_answer
    return update
