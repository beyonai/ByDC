"""user_clarify_node：对用户澄清回复做格式化，将结果写入 clarification_formatted_params。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _format_clarification,
)

logger = logging.getLogger(__name__)


def _extract_resume_value(state: AgentState) -> Any:
    """从 state.messages 最后一条 HumanMessage 提取用户回复内容。"""
    messages = list(state.get("messages") or [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        if isinstance(msg, dict) and msg.get("type") == "human":
            return msg.get("content", "")
    return None


async def user_clarify_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """读取用户澄清回复，调用 _format_clarification 格式化，写入 clarification_formatted_params。

    完成后清理 pending_clarification_context 和 clarification_analyze_result。
    """
    ctx = dict(state.get("pending_clarification_context") or {})
    analyze_result = dict(state.get("clarification_analyze_result") or {})

    tool_name = str(ctx.get("tool_name") or analyze_result.get("tool_name") or "")
    query = str(ctx.get("query") or analyze_result.get("query") or "")
    structured_input = dict(
        ctx.get("structured_input") or analyze_result.get("structured_input") or {}
    )
    is_compute: bool = bool(ctx.get("is_compute") or analyze_result.get("is_complex"))
    clarify_knowledge = str(analyze_result.get("clarify_knowledge") or "")

    resume_value = _extract_resume_value(state)
    form_str = json.dumps(resume_value, ensure_ascii=False) if resume_value else "{}"

    logger.info(
        "[user_clarify] tool=%s is_compute=%s form_str_len=%d",
        tool_name,
        is_compute,
        len(form_str),
    )

    formatted_params = _format_clarification(
        query,
        structured_input,
        form_str,
        clarify_knowledge,
        is_compute=is_compute,
    )

    clarification_formatted_params: dict[str, Any] = {
        "tool_name": tool_name,
        "is_complex": is_compute,
        "params": formatted_params,
    }

    logger.info("[user_clarify] formatted params keys=%s", sorted(formatted_params.keys()))

    return {
        "clarification_formatted_params": clarification_formatted_params,
        "pending_clarification_context": None,
        "clarification_analyze_result": None,
    }
