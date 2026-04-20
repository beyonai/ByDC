"""analyze_clarify_node：调用 SDK 分析澄清需求，将结果写入 state。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _analyze_clarification,
    _apply_resolved_to_params,
)

logger = logging.getLogger(__name__)


async def analyze_clarify_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """从 pending_clarification_context 读取上下文，调用 SDK 分析澄清需求。

    paradigm_list 非空 → 需要用户确认，写入 clarification_analyze_result。
    paradigm_list 为空 → 直接生成 pre_filled_params 供 tool_dispatcher resume 使用。
    """
    ctx = dict(state.get("pending_clarification_context") or {})
    tool_name = str(ctx.get("tool_name") or "")
    query = str(ctx.get("query") or "")
    structured_input = dict(ctx.get("structured_input") or {})
    is_compute: bool = bool(ctx.get("is_compute"))
    ontology_code = str(
        ctx.get("ontology_code") or tool_name.replace("query_", "").replace("compute_", "")
    )

    logger.info(
        "[analyze_clarify] tool=%s is_compute=%s ontology_code=%s",
        tool_name,
        is_compute,
        ontology_code,
    )

    paradigm_list, clarify_knowledge = _analyze_clarification(
        query, ontology_code, structured_input, is_compute=is_compute
    )

    analyze_result: dict[str, Any] = {
        "paradigm_list": paradigm_list,
        "clarify_knowledge": clarify_knowledge,
        "is_complex": is_compute,
        "tool_name": tool_name,
        "query": query,
        "structured_input": structured_input,
    }

    if not paradigm_list:
        # 无需澄清：直接 apply resolved（resolved 为空时原样返回）
        pre_filled = _apply_resolved_to_params(structured_input, {})
        analyze_result["pre_filled_params"] = pre_filled

    logger.info(
        "[analyze_clarify] paradigm_list_count=%d knowledge_len=%d",
        len(paradigm_list),
        len(clarify_knowledge),
    )

    return {"clarification_analyze_result": analyze_result}
