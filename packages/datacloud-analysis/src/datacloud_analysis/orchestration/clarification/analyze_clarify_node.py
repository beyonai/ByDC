"""analyze_clarify_node：分析澄清需求，将结果写入 state。"""

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
    """分析澄清需求，优先复用 ClarificationNeededError 中的缓存数据（避免重复 SDK 调用）。

    V0.3：ClarificationNeededError.context 已包含 paradigm_list / clarify_knowledge，
    直接复用，跳过昂贵的 _analyze_clarification() 调用（节省 15-22 秒）。
    fallback：若 pending_clarification_context 中无缓存，则调用 SDK。
    """
    ctx = dict(state.get("pending_clarification_context") or {})
    tool_name = str(ctx.get("tool_name") or "")
    query = str(ctx.get("query") or "")
    structured_input = dict(ctx.get("structured_input") or {})
    is_compute: bool = bool(ctx.get("is_compute"))

    # V0.3 快速路径：ClarificationNeededError.context 已含 paradigm_list
    cached_paradigm_list = ctx.get("paradigm_list")
    if cached_paradigm_list is not None:
        paradigm_list: list[dict[str, Any]] = list(cached_paradigm_list)
        clarify_knowledge = str(ctx.get("clarify_knowledge") or "")
        logger.info(
            "[analyze_clarify] V0.3 cache hit: tool=%s paradigm_count=%d",
            tool_name,
            len(paradigm_list),
        )
    else:
        ontology_code = str(
            ctx.get("ontology_code") or tool_name.replace("query_", "").replace("compute_", "")
        )
        logger.info(
            "[analyze_clarify] SDK fallback: tool=%s is_compute=%s ontology_code=%s",
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
        analyze_result["pre_filled_params"] = _apply_resolved_to_params(structured_input, {})

    logger.info(
        "[analyze_clarify] paradigm_list_count=%d knowledge_len=%d",
        len(paradigm_list),
        len(clarify_knowledge),
    )

    return {"clarification_analyze_result": analyze_result}
