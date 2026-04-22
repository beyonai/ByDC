"""finish_react_node：处理 ReAct 循环结束，构造 react_final，清理 ReAct 状态。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.message_util import extract_ai_text
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _try_parse_records_block(content: str) -> dict[str, Any] | None:
    """从 ToolMessage content 中解析 records+meta 结构，返回 query_data 或 None。"""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    data_block = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    if (
        isinstance(data_block, dict)
        and isinstance(data_block.get("records"), list)
        and "meta" in data_block
    ):
        return data_block
    return None


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
            last_content = extract_ai_text(msg.content)
            calls = list(getattr(msg, "tool_calls", None) or [])
            for tc in calls:
                if tc.get("name") == "finish_react":
                    finish_args = dict(tc.get("args") or {})
                    break
            break

    result_type = str(finish_args.get("result_type") or "text")
    answer = str(finish_args.get("answer") or last_content or "")
    stop_reason = status if status else "finish_react"
    csv_file_path = str(finish_args.get("csv_file_path") or "")
    answer_streamed = bool(state.get("answer_streamed"))

    _last_query_data: dict[str, Any] | None = state.get("react_last_query_data")

    # 有缓存的 query_data 时，自动升级 result_type 为 query_result，
    # 避免 LLM 误选 text 导致数据列表丢失。
    if _last_query_data is not None and result_type == "text":
        result_type = "query_result"

    # Fallback：blob 持久化失败或跨轮次清除导致 react_last_query_data 丢失时，
    # 回扫 messages 中最近一条含 records+meta 的 ToolMessage 恢复数据。
    if _last_query_data is None and result_type in {"query_result", "text"}:
        for msg in reversed(messages):
            if not isinstance(msg, ToolMessage):
                continue
            if (getattr(msg, "name", "") or "") == "finish_react":
                continue
            recovered = _try_parse_records_block(str(msg.content or ""))
            if recovered is not None:
                _last_query_data = recovered
                result_type = "query_result"
                logger.info(
                    "[finish_react] recovered query_data from messages records=%d",
                    len(recovered.get("records") or []),
                )
                break

    logger.info("[finish_react] result_type=%s stop_reason=%s", result_type, stop_reason)

    react_final: dict[str, Any] = {
        "result_type": result_type,
        "answer": answer,
        "stop_reason": stop_reason,
        "csv_file_path": csv_file_path,
        "answer_streamed": answer_streamed,
    }
    if _last_query_data is not None and result_type in {"query_result", "csv_file", "json_file"}:
        react_final["query_data"] = _last_query_data

    return {
        "react_final": react_final,
        "react_rounds": int(state.get("react_round_idx") or 0),
        "react_messages_log": None,
        "react_round_idx": None,
        "react_last_query_data": None,
        "answer_streamed": None,
        "execution_status": None,
    }
