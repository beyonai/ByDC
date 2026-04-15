"""Query clarification — NL → 展开 → 召回 → LLM确认 → paradigmList 全流程。

流程：
    NL → LLM 展开 (NatQuery) → 转五段式 → 按类型召回
    → LLM 确认（选择/重构/标记歧义）
    → ClarificationResult（form 或 knowledge）

调用方式::

    from datacloud_knowledge.intent import analyze_query_clarification
    result = analyze_query_clarification("202602龙头、骨干企业的数量、营收")
"""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .llm_confirm import ConfirmedQuery, llm_confirm
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
    """将 ConfirmedQuery 转为 paradigmList 格式（兼容前端协议）。"""
    # 收集需要澄清的 keyword 集合，用于避免重复
    clarify_keywords = {ci.keyword for ci in cq.clarify_items}

    # paradigmId=1: 查询值 (SELECT)
    # confirmed 项 — 排除已在 clarify_items 中的（避免重复）
    select_result: list[dict[str, Any]] = []
    kid = 0
    for s in cq.select:
        original = s.original_keyword or s.expr
        if original in clarify_keywords:
            continue  # 会在 clarify_items 中展示，跳过
        kid += 1
        select_result.append({
            "keyword": original,
            "recall": [s.expr] if s.expr != original else [],
            "choiceKeyword": s.expr,
            "kid": kid,
            "ktype": "select",
        })
    # clarify 项 — 展示候选列表供用户选择
    for ci in cq.clarify_items:
        kid += 1
        select_result.append({
            "keyword": ci.keyword,
            "recall": ci.candidates,
            "kid": kid,
            "ktype": "select",
        })

    # paradigmId=2: 分组条件 (GROUP BY)
    group_result = [
        {"keyword": g, "recall": [], "kid": i, "ktype": "groupBy"}
        for i, g in enumerate(cq.group_by, start=1)
    ]

    # paradigmId=3: 过滤条件 (WHERE)
    filter_result: list[dict[str, Any]] = []
    for w in cq.where:
        if isinstance(w.value, list):
            display_value = ", ".join(str(v) for v in w.value)
        else:
            display_value = str(w.value)
        filter_result.append({
            "type": "predicate",
            "field": w.field,
            "fieldRecall": [],
            "comparison": w.op if w.op != "=" else "eq",
            "value": display_value,
            "valueRecall": [],
        })

    # paradigmId=4: 排序目标
    order_result = [
        {"keyword": o, "recall": [], "kid": i, "ktype": "orderBy"}
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


def analyze_query_clarification(query: str) -> ClarificationResult:
    """分析查询是否需要用户澄清。

    完整流程：NL → LLM展开 → 召回 → LLM确认 → ClarificationResult。

    Args:
        query: 用户原始自然语言查询。

    Returns:
        ClarificationResult:
          - needs_clarification=True + form: 需要用户确认的 paradigmList
          - needs_clarification=False + knowledge: LLM 确认完毕的 paradigmList
          - LLM 失败时透传 ClarificationResult(query=query)
    """
    # Step 1: LLM 展开 + 结构化
    natquery = expand_query(query)
    if natquery is None:
        logger.warning("[clarification] LLM 展开失败，返回原始查询")
        return ClarificationResult(query=query)

    expanded_query = natquery.query
    logger.info("[clarification] Step1 展开完成: %s", expanded_query)

    # Step 2: NatQuery → 五段式 → 召回
    five_stage_raw = natquery_to_five_stage(natquery)
    structured_query = five_stage_keys_from_raw(five_stage_raw)

    try:
        state = build_paradigm_resolution_state(
            original_question=query,
            structured_query=structured_query,
        )
    except Exception:
        logger.exception("[clarification] Step2 召回失败，返回展开结果")
        return ClarificationResult(query=expanded_query)

    logger.info(
        "[clarification] Step2 召回完成: items=%d, resolved=%d",
        len(state.items),
        sum(1 for it in state.items if it.is_resolved),
    )

    # Step 3: LLM 确认 — 基于召回结果生成真实 schema 查询
    confirmed = llm_confirm(
        original_question=query,
        expanded_query=expanded_query,
        state=state,
    )

    if confirmed is None:
        # LLM 确认失败 → fallback 到纯召回结果
        logger.warning("[clarification] Step3 LLM确认失败，fallback 到召回结果")
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

    # Step 4: 构建 paradigmList
    paradigm_list = _confirmed_query_to_paradigm_list(confirmed)

    if confirmed.needs_clarification:
        logger.info(
            "[clarification] Step4 需要澄清: %d 项",
            len(confirmed.clarify_items),
        )
        return ClarificationResult(
            query=expanded_query,
            needs_clarification=True,
            form=_serialize_payload({"paradigmList": paradigm_list}),
        )

    logger.info("[clarification] Step4 LLM确认完毕，无需澄清")
    return ClarificationResult(
        query=expanded_query,
        knowledge=_serialize_payload({"paradigmList": paradigm_list}),
    )
