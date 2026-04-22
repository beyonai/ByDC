from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.intend.command_router import CommandRouter
from datacloud_analysis.orchestration.message_util import last_human_text
from datacloud_analysis.orchestration.state import AgentState

_router = CommandRouter()
logger = logging.getLogger(__name__)


def _trace_user_query_enabled() -> bool:
    return os.environ.get("DATACLOUD_TRACE_USER_QUERY", "").strip().lower() in ("1", "true", "yes")


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
    # 必须用「最后一条用户话」，不能取 messages[-1]：合并后的 state 常以 AIMessage 结尾，
    # 否则会误把助手回复当作用户问题，表现为意图/识别永远像第一轮。
    user_query = last_human_text(messages)

    if _trace_user_query_enabled():
        gw = config.get("configurable") or {}
        gctx = gw.get("gateway_context")
        sid = getattr(gctx, "session_id", "") if gctx is not None else ""
        tail_type = type(messages[-1]).__name__ if messages else "empty"
        logger.info(
            "[user_query_trace] intend_node session=%s messages_n=%d tail_msg_type=%s "
            "resolved_user_query_len=%d resolved_preview=%r",
            sid,
            len(messages),
            tail_type,
            len(user_query),
            user_query[:400] + ("..." if len(user_query) > 400 else ""),
        )
        for idx, m in enumerate(messages):
            logger.info(
                "[user_query_trace] intend_node msg[%d] %s",
                idx,
                _message_line_preview(m, max_len=160),
            )

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
