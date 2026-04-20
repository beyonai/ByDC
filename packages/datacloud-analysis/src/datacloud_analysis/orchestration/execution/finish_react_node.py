"""finish_react_node：处理 ReAct 循环结束，构造 react_final，清理 ReAct 状态。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def finish_react_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """从 state["messages"] 最后一条 AIMessage 提取 finish_react 参数，构造 react_final。

    清理 react_round_idx / execution_status；react_messages_log 已不使用但仍置 None 以清理残留。
    """
    status = str(state.get("execution_status") or "")
    messages = list(state.get("messages") or [])

    # 从最后一条 AIMessage 的 tool_calls 提取 finish_react 参数
    finish_args: dict[str, Any] = {}
    last_content = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_content = str(msg.content or "")
            calls = list(getattr(msg, "tool_calls", None) or [])
            for tc in calls:
                if tc.get("name") == "finish_react":
                    finish_args = dict(tc.get("args") or {})
                    break
            break

    result_type = str(finish_args.get("result_type") or "text")
    answer = str(finish_args.get("answer") or last_content or "")
    stop_reason = status if status else "finish_react"

    logger.info("[finish_react] result_type=%s stop_reason=%s", result_type, stop_reason)

    return {
        "react_final": {
            "result_type": result_type,
            "answer": answer,
            "stop_reason": stop_reason,
        },
        "react_rounds": int(state.get("react_round_idx") or 0),
        "react_messages_log": None,
        "react_round_idx": None,
        "execution_status": None,
    }
