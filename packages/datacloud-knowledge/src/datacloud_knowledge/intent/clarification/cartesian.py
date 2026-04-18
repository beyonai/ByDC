"""笛卡尔积展开 + paradigmList 构建。

complex_conditions 中未确定的术语做笛卡尔积展开（上限 20），
已确定的术语加括号注释但不参与组合。

主结构未确定术语按 paradigmId 分组构建 paradigmList。
"""

from __future__ import annotations

import itertools
import json
import logging
from typing import Any

from .models import (
    ConditionTermMapping,
    ConfirmedCondition,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    KnowledgeMeta,
)

logger = logging.getLogger(__name__)

MAX_COMBINATIONS = 20


# ── 笛卡尔积展开 ─────────────────────────────────────────────────────


def truncate_candidates(
    unconfirmed: list[ConditionTermMapping],
    max_combinations: int = MAX_COMBINATIONS,
) -> list[list[str]]:
    """按候选排名截断，确保笛卡尔积 ≤ max_combinations。

    从候选最多的术语开始，逐步裁剪末尾候选。

    Args:
        unconfirmed: 未确定的术语映射列表（confirmed is None）。
        max_combinations: 组合上限。

    Returns:
        每个术语的截断后候选列表。
    """
    if not unconfirmed:
        return []

    candidate_lists = [tm.candidates[:] for tm in unconfirmed]

    # 逐步裁剪，直到积 ≤ max_combinations
    while True:
        product = 1
        for cl in candidate_lists:
            product *= max(len(cl), 1)
        if product <= max_combinations:
            break

        # 找候选最多的术语，裁剪末尾
        max_idx = max(range(len(candidate_lists)), key=lambda i: len(candidate_lists[i]))
        if len(candidate_lists[max_idx]) <= 1:
            break  # 无法再裁剪
        candidate_lists[max_idx].pop()

    return candidate_lists


def expand_condition_cartesian(
    condition: ConfirmedCondition,
    max_combinations: int = MAX_COMBINATIONS,
) -> list[str]:
    """对单条 complex_condition 做笛卡尔积展开。

    已确定术语：替换为 "原词（确认词）"，不参与组合。
    未确定术语：candidates 参与笛卡尔积。
    全部确定 → 返回单个句子（仍加括号注释）。

    Args:
        condition: LLM 确认后的单条 condition。
        max_combinations: 组合上限。

    Returns:
        展开后的句子列表。
    """
    sentence = condition.original_sentence
    if not condition.term_mappings:
        return [sentence]

    # 分离已确定 / 未确定
    confirmed_mappings: list[ConditionTermMapping] = []
    unconfirmed_mappings: list[ConditionTermMapping] = []
    for tm in condition.term_mappings:
        if tm.confirmed is not None:
            confirmed_mappings.append(tm)
        elif tm.candidates:
            unconfirmed_mappings.append(tm)

    # 截断未确定术语的候选
    if unconfirmed_mappings:
        truncated = truncate_candidates(unconfirmed_mappings, max_combinations)
    else:
        truncated = []

    # 构建笛卡尔积
    combos = list(itertools.product(*truncated)) if truncated else [()]  # 全部确定，单个组合

    results: list[str] = []
    for combo in combos:
        result = _apply_replacements(sentence, confirmed_mappings, unconfirmed_mappings, combo)
        results.append(result)

    return results


def _apply_replacements(
    sentence: str,
    confirmed: list[ConditionTermMapping],
    unconfirmed: list[ConditionTermMapping],
    combo: tuple[str, ...],
) -> str:
    """按 start/end 位置替换术语，生成带括号注释的句子。"""
    # 合并所有替换，按 start 降序排列（从后往前替换，避免位移）
    replacements: list[tuple[int, int, str, str]] = []

    for tm in confirmed:
        replacements.append((tm.start, tm.end, tm.original_term, tm.confirmed or ""))

    for i, tm in enumerate(unconfirmed):
        if i < len(combo):
            replacements.append((tm.start, tm.end, tm.original_term, combo[i]))

    # 按 start 降序
    replacements.sort(key=lambda r: r[0], reverse=True)

    result = sentence
    for start, end, original, replacement in replacements:
        annotated = f"{original}（{replacement}）"
        result = result[:start] + annotated + result[end:]

    return result


# ── paradigmList 构建 ────────────────────────────────────────────────


def build_paradigm_list(
    confirmed: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    *,
    complex_conditions: list[str] | None = None,
) -> tuple[list[dict[str, Any]], KnowledgeMeta]:
    """构建 paradigmList + 内部元数据。

    Args:
        confirmed: LLM 确认后的结构。
        terms: 提取的术语列表。
        recall_map: 召回结果。
        complex_conditions: 原始 complex_conditions 列表。

    Returns:
        (paradigmList, KnowledgeMeta) 元组。
    """
    mode = "query" if isinstance(confirmed, ConfirmedStructuredQuery) else "compute"
    path_mapping: dict[str, str] = {}

    # 收集需要澄清的 keyword 集合
    clarify_keywords = {ci.keyword for ci in confirmed.clarify_items}

    # paradigmId=1: 查询值（按 raw_text 去重，同名术语合并 path）
    select_result: list[dict[str, Any]] = []
    kid = 0
    seen_select: dict[str, int] = {}  # raw_text → kid，用于去重 + path 合并
    select_terms = [t for t in terms if t.ktype == "select" and t.source == "main"]
    for term in select_terms:
        if term.raw_text in clarify_keywords:
            continue
        if term.raw_text in seen_select:
            # 同名术语：追加 path（逗号分隔），不生成新行
            existing_kid = seen_select[term.raw_text]
            path_mapping[str(existing_kid)] += f",{term.path}"
            continue
        kid += 1
        seen_select[term.raw_text] = kid
        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        recall_names = [str(c.get("term_name", "")) for c in candidates[:5]]
        item: dict[str, Any] = {
            "keyword": term.raw_text,
            "recall": recall_names,
            "kid": kid,
            "ktype": "select",
        }
        # 单候选 → 自动确认
        if len(recall_names) == 1:
            item["choiceKeyword"] = recall_names[0]
        path_mapping[str(kid)] = term.path
        select_result.append(item)

    # clarify_items → 按 source 分发到对应 paradigm（延迟追加，先收集）
    _clarify_for_group: list[dict[str, Any]] = []
    _clarify_for_filter: list[dict[str, Any]] = []
    _clarify_for_order: list[dict[str, Any]] = []
    for ci in confirmed.clarify_items:
        kid += 1
        ci_source = ci.source or "select"
        ci_item: dict[str, Any] = {
            "keyword": ci.keyword,
            "recall": ci.candidates,
            "kid": kid,
            "ktype": ci_source,
            "source": ci.source,
        }
        path_mapping[str(kid)] = ci.path
        if ci_source in ("where", "whereKey", "whereValue"):
            _clarify_for_filter.append(ci_item)
        elif ci_source in ("group_by", "groupBy"):
            _clarify_for_group.append(ci_item)
        elif ci_source in ("order_by", "orderBy"):
            _clarify_for_order.append(ci_item)
        else:
            # select 或未知 → 默认查询值
            select_result.append(ci_item)

    # paradigmId=2: 分组条件
    group_result: list[dict[str, Any]] = []
    group_terms = [t for t in terms if t.ktype == "groupBy" and t.source == "main"]
    for i, term in enumerate(group_terms, start=1):
        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        recall_names = [str(c.get("term_name", "")) for c in candidates[:5]]
        item = {
            "keyword": term.raw_text,
            "recall": recall_names,
            "kid": i,
            "ktype": "groupBy",
        }
        if len(recall_names) == 1:
            item["choiceKeyword"] = recall_names[0]
        path_mapping[f"g{i}"] = term.path
        group_result.append(item)
    group_result.extend(_clarify_for_group)

    # paradigmId=3: 过滤条件
    filter_result: list[dict[str, Any]] = []
    _build_filter_paradigm(terms, recall_map, filter_result, path_mapping)

    # complex_conditions → paradigmId=3 的 IFieldItem
    if complex_conditions and confirmed.confirmed_conditions:
        for idx, cc in enumerate(confirmed.confirmed_conditions):
            original = (
                complex_conditions[idx] if idx < len(complex_conditions) else cc.original_sentence
            )
            expanded = expand_condition_cartesian(cc)
            filter_result.append(
                {
                    "keyword": original,
                    "recall": expanded,
                    "kid": len(filter_result) + 1,
                    "ktype": "complexCondition",
                }
            )
    filter_result.extend(_clarify_for_filter)

    # paradigmId=4: 排序目标
    order_result: list[dict[str, Any]] = []
    order_terms = [t for t in terms if t.ktype == "orderBy" and t.source == "main"]
    for i, term in enumerate(order_terms, start=1):
        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        recall_names = [str(c.get("term_name", "")) for c in candidates[:5]]
        item = {
            "keyword": term.raw_text,
            "recall": recall_names,
            "kid": i,
            "ktype": "orderBy",
        }
        if len(recall_names) == 1:
            item["choiceKeyword"] = recall_names[0]
        path_mapping[f"o{i}"] = term.path
        order_result.append(item)
    order_result.extend(_clarify_for_order)

    # paradigmId=5: 统计函数（空）
    agg_result: list[dict[str, Any]] = []

    paradigm_list = [
        {"paradigmId": "1", "paradigmName": "查询值", "paradigmResult": select_result},
        {"paradigmId": "2", "paradigmName": "分组条件", "paradigmResult": group_result},
        {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": filter_result},
        {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": order_result},
        {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": agg_result},
    ]

    meta = KnowledgeMeta(
        path_mapping=path_mapping,
        confirmed_conditions=confirmed.confirmed_conditions,
        mode=mode,  # type: ignore[arg-type]
    )

    return paradigm_list, meta


def _build_filter_paradigm(
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    filter_result: list[dict[str, Any]],
    path_mapping: dict[str, str],
) -> None:
    """构建过滤条件的 paradigmResult（IConditionItem 格式）。"""
    # 按 path 前缀配对 whereKey + whereValue
    key_terms = [t for t in terms if t.ktype == "whereKey" and t.source == "main"]
    value_terms = [t for t in terms if t.ktype == "whereValue" and t.source == "main"]

    # 简单配对：按 filters 索引
    paired: dict[str, dict[str, ExtractedTerm]] = {}
    for t in key_terms:
        # path 如 "filters.0.field" → 提取 "filters.0"
        parts = t.path.rsplit(".", 1)
        prefix = parts[0] if len(parts) > 1 else t.path
        paired.setdefault(prefix, {})["key"] = t
    for t in value_terms:
        parts = t.path.rsplit(".", 1)
        prefix = parts[0] if len(parts) > 1 else t.path
        paired.setdefault(prefix, {})["value"] = t

    for prefix in sorted(paired):
        pair = paired[prefix]
        key_term = pair.get("key")
        value_term = pair.get("value")
        if key_term is None:
            continue

        key_key = f"{key_term.ktype}:{key_term.raw_text}"
        key_candidates = recall_map.get(key_key, [])
        key_names = [str(c.get("term_name", "")) for c in key_candidates[:5]]

        item: dict[str, Any] = {
            "field": key_term.raw_text,
            "fieldRecall": key_names,
            "comparison": "eq",
        }
        if len(key_names) == 1:
            item["choiceField"] = key_names[0]

        if value_term:
            val_key = f"{value_term.ktype}:{value_term.raw_text}"
            val_candidates = recall_map.get(val_key, [])
            val_names = [str(c.get("term_name", "")) for c in val_candidates[:5]]
            item["value"] = value_term.raw_text
            item["valueRecall"] = val_names
            if len(val_names) == 1:
                item["choiceValue"] = val_names[0]
        else:
            item["value"] = ""
            item["valueRecall"] = []

        path_mapping[f"f{prefix}"] = key_term.path
        filter_result.append(item)


def serialize_paradigm_payload(
    paradigm_list: list[dict[str, Any]],
) -> str:
    """序列化 paradigmList 为 JSON 字符串。"""
    return json.dumps({"paradigmList": paradigm_list}, ensure_ascii=False)


def serialize_knowledge_meta(meta: KnowledgeMeta) -> str:
    """序列化 KnowledgeMeta 为 JSON 字符串。"""
    return meta.model_dump_json()
