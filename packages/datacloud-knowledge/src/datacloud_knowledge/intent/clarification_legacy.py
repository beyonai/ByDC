"""Query clarification — NL → 展开 → 召回 → LLM确认 → paradigmList 全流程。

流程：
    NL → LLM 展开 (NatQuery) → 转五段式 → 按类型召回
    → LLM 确认（选择/重构/标记歧义）
    → ClarificationResult（form 或 knowledge）

调用方式::

    from datacloud_knowledge.intent import analyze_query_clarification
    result = analyze_query_clarification("202602龙头、骨干企业的数量、营收")
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .llm_confirm import (
    ConfirmedQuery,
    _format_recall_context,
    llm_confirm,
    semantic_to_display,
    semantic_to_sql_expr,
)
from .llm_utils import EventEmitter
from .natquery import expand_query, natquery_to_five_stage
from .paradigm_builder import build_paradigm_resolution_state, five_stage_keys_from_raw
from .types import ClarificationResult

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


def _serialize_payload(payload: Mapping[str, Any] | None) -> str:
    if payload is None:
        return ""
    return json.dumps(payload, ensure_ascii=False)


def _confirmed_query_to_paradigm_list(cq: ConfirmedQuery) -> list[dict[str, Any]]:
    """将 ConfirmedQuery 转为 paradigmList 格式（兼容前端协议）。

    语义化 SELECT 项会同时输出：
    - choiceKeyword: 还原后的 SQL 表达式（供下游执行）
    - displayText: 用户可读的语义化描述（供前端展示）
    - semantic: 结构化语义组件（供前端编辑/还原）
    """
    # 收集需要澄清的 keyword 集合，用于避免重复
    clarify_keywords = {ci.keyword for ci in cq.clarify_items}

    # paradigmId=1: 查询值 (SELECT)
    # confirmed 项 — 排除已在 clarify_items 中的（避免重复）
    select_result: list[dict[str, Any]] = []
    kid = 0
    for s in cq.select:
        original = s.original_keyword or s.measure
        if original in clarify_keywords:
            continue  # 会在 clarify_items 中展示，跳过
        kid += 1
        sql_expr = semantic_to_sql_expr(s)
        display_text = semantic_to_display(s)
        select_result.append(
            {
                "keyword": original,
                "recall": [sql_expr] if sql_expr != original else [],
                "choiceKeyword": sql_expr,
                "displayText": display_text,
                "semantic": {
                    "measure": s.measure,
                    "denominator": s.denominator,
                    "agg_func": s.agg_func,
                    "filters": [f.model_dump() for f in s.filters],
                },
                "kid": kid,
                "ktype": "select",
            }
        )
    # clarify 项 — 展示候选列表供用户选择
    for ci in cq.clarify_items:
        kid += 1
        target_list = select_result  # 默认放 select
        ktype = ci.source or "select"
        target_list.append(
            {
                "keyword": ci.keyword,
                "recall": ci.candidates,
                "kid": kid,
                "ktype": ktype,
                "source": ci.source,
            }
        )

    # paradigmId=2: 分组条件 (GROUP BY)
    group_result = [
        {
            "keyword": g.original_keyword or g.field,
            "choiceKeyword": g.field,
            "recall": [g.field] if g.original_keyword and g.original_keyword != g.field else [],
            "kid": i,
            "ktype": "groupBy",
        }
        for i, g in enumerate(cq.group_by, start=1)
    ]

    # paradigmId=3: 过滤条件 (WHERE)
    filter_result: list[dict[str, Any]] = []
    for w in cq.where:
        if isinstance(w.value, list):
            display_value = ", ".join(str(v) for v in w.value)
        else:
            display_value = str(w.value)
        # field: 展示名（用户原文 > 真实字段名）
        # fieldRecall: 真实字段名候选（展示名≠真实名时才填）
        display_field = w.original_field_keyword or w.field
        field_recall: list[str] = [w.field] if display_field != w.field else []
        # value: 展示值（用户原文 > 实际值）
        display_val = w.original_value_keyword or display_value
        value_recall: list[str] = [display_value] if display_val != display_value else []
        filter_result.append(
            {
                "field": display_field,
                "fieldRecall": field_recall,
                "comparison": w.op if w.op != "=" else "eq",
                "value": display_val,
                "valueRecall": value_recall,
            }
        )

    # paradigmId=4: 排序目标
    order_result = [
        {
            "keyword": o.original_keyword or o.field,
            "choiceKeyword": f"{o.field} {o.direction}",
            "recall": [o.field] if o.original_keyword and o.original_keyword != o.field else [],
            "kid": i,
            "ktype": "orderBy",
        }
        for i, o in enumerate(cq.order_by, start=1)
    ]

    # paradigmId=5: 统计函数（空，已折叠进 select）
    agg_result: list[dict[str, Any]] = []

    return [
        {"paradigmId": "1", "paradigmName": "查询值", "paradigmResult": select_result},
        {"paradigmId": "2", "paradigmName": "分组条件", "paradigmResult": group_result},
        {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": filter_result},
        {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": order_result},
        {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": agg_result},
    ]


def analyze_query_clarification(
    query: str,
    on_event: Callable[[Any], None] | None = None,
) -> ClarificationResult:
    """分析查询是否需要用户澄清。

    完整流程：NL → LLM展开 → 召回 → LLM确认 → ClarificationResult。

    Args:
        query: 用户原始自然语言查询。
        on_event: 可选回调，接收 StreamEvent 实例（标题/工具名/入参/思考/返回/错误）。

    Returns:
        ClarificationResult:
          - needs_clarification=True + form: 需要用户确认的 paradigmList
          - needs_clarification=False + knowledge: LLM 确认完毕的 paradigmList
          - LLM 失败时透传 ClarificationResult(query=query)
    """
    emit = EventEmitter(on_event)

    # ── Step 1: LLM 展开 + 结构化 ──
    with emit.step("查询分析", "expand_query", {"query": query}):
        natquery = expand_query(query, on_event=on_event)
        if natquery is None:
            logger.warning("[clarification] LLM 展开失败，返回原始查询")
            emit.error("LLM 展开失败")
            return ClarificationResult(query=query)
        emit.result(natquery.model_dump())

    expanded_query = natquery.query
    logger.info("[clarification] Step1 展开完成: %s", expanded_query)

    # ── Step 2: NatQuery → 五段式 → 召回 ──
    five_stage_raw = natquery_to_five_stage(natquery)
    structured_query = five_stage_keys_from_raw(five_stage_raw)

    with emit.step("知识召回", "knowledge_recall", structured_query):
        try:
            state = build_paradigm_resolution_state(
                original_question=query,
                structured_query=structured_query,
            )
        except Exception:
            logger.exception("[clarification] Step2 召回失败，返回展开结果")
            emit.error("知识召回失败")
            return ClarificationResult(query=expanded_query)

        recall_summary = {
            "items": len(state.items),
            "resolved": sum(1 for it in state.items if it.is_resolved),
        }
        emit.result(recall_summary)

    logger.info(
        "[clarification] Step2 召回完成: items=%d, resolved=%d",
        recall_summary["items"],
        recall_summary["resolved"],
    )

    # ── Step 3: LLM 确认 ──
    with emit.step(
        "查询确认",
        "llm_confirm",
        {
            "original_question": query,
            "expanded_query": expanded_query,
        },
    ):
        confirmed = llm_confirm(
            original_question=query,
            expanded_query=expanded_query,
            recall_context=_format_recall_context(
                state.items,
                dimension_value_hints=state.dimension_value_hints,
            ),
            on_event=on_event,
        )
        if confirmed is None:
            logger.warning("[clarification] Step3 LLM确认失败，fallback 到召回结果")
            emit.error("LLM 确认失败，使用召回结果兜底")
            paradigm_list = state.build_paradigm_list()
            unresolved = state.unresolved_items()
            if unresolved:
                return ClarificationResult(
                    query=expanded_query,
                    needs_clarification=True,
                    form=_serialize_payload({"paradigmList": paradigm_list}),
                )
            return ClarificationResult(
                query=expanded_query,
                knowledge=_serialize_payload({"paradigmList": paradigm_list}),
            )

        emit.result(
            {
                "select": [
                    {
                        "measure": s.measure,
                        "agg_func": s.agg_func,
                        "filters": [f.model_dump() for f in s.filters],
                        "sql_expr": semantic_to_sql_expr(s),
                    }
                    for s in confirmed.select
                ],
                "where": [
                    {
                        "field": w.field,
                        "op": w.op,
                        "value": w.value,
                        "original_field_keyword": w.original_field_keyword,
                        "original_value_keyword": w.original_value_keyword,
                    }
                    for w in confirmed.where
                ],
                "group_by": [
                    {"field": g.field, "original_keyword": g.original_keyword}
                    for g in confirmed.group_by
                ],
                "order_by": [
                    {
                        "field": o.field,
                        "direction": o.direction,
                        "original_keyword": o.original_keyword,
                    }
                    for o in confirmed.order_by
                ],
                "needs_clarification": confirmed.needs_clarification,
            }
        )

    # ── Step 4: 构建 paradigmList ──
    with emit.step("结果生成", "build_paradigm_list"):
        paradigm_list = _confirmed_query_to_paradigm_list(confirmed)
        payload = _serialize_payload({"paradigmList": paradigm_list})
        emit.result(payload)

    if confirmed.needs_clarification:
        logger.info("[clarification] Step4 需要澄清: %d 项", len(confirmed.clarify_items))
        return ClarificationResult(
            query=expanded_query,
            needs_clarification=True,
            form=payload,
        )

    logger.info("[clarification] Step4 LLM确认完毕，无需澄清")
    return ClarificationResult(query=expanded_query, knowledge=payload)
