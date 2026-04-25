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


def _clear_messages_update() -> dict[str, list[RemoveMessage]]:
    """Build a LangGraph update that clears accumulated conversation messages."""
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)]}


async def respond_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    react_final = state.get("react_final") or {}
    workspace_dir = state.get("workspace_dir")

    # [DIAG] 诊断日志：确认 respond_node 收到的是当前轮还是上一轮的 react_final
    _qd = react_final.get("query_data") or {}
    _records = _qd.get("records") or [] if isinstance(_qd, dict) else []
    _first_rec = str(_records[0])[:80] if _records else "N/A"
    logger.warning(
        "[respond_node DIAG] result_type=%s answer_streamed=%s answer_preview=%r "
        "has_query_data=%s records_n=%d first_record_preview=%s",
        react_final.get("result_type"),
        react_final.get("answer_streamed"),
        str(react_final.get("answer") or "")[:80],
        bool(react_final.get("query_data")),
        len(_records),
        _first_rec,
    )
    logger.warning(
        "[respond_node DIAG] gw_ctx.message_id=%s gw_ctx.parent_message_id=%s",
        getattr(gw_ctx, "message_id", "N/A"),
        getattr(gw_ctx, "parent_message_id", "N/A"),
    )

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

    await format_result(react_final, gw_ctx, workspace_dir)
    return _clear_messages_update()
