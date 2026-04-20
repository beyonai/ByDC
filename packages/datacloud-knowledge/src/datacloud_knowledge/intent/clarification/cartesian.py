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
    ClarifyItem,
    ConditionTermMapping,
    ConfirmedCondition,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    KnowledgeMeta,
)

logger = logging.getLogger(__name__)

MAX_COMBINATIONS = 20

# 合法运算符候选（与 WhereClause.op 一致）
_ALL_COMPARISON_OPS: list[str] = ["eq", "gt", "lt", "gte", "lte", "in", "between"]

# op 值标准化映射
_OP_NORMALIZE: dict[str, str] = {
    "=": "eq",
    "==": "eq",
    "eq": "eq",
    ">": "gt",
    "gt": "gt",
    "<": "lt",
    "lt": "lt",
    ">=": "gte",
    "gte": "gte",
    "<=": "lte",
    "lte": "lte",
    "in": "in",
    "IN": "in",
    "between": "between",
    "BETWEEN": "between",
}


def _normalize_op(raw_op: str) -> str:
    """将各种 op 表示标准化为前端 key。"""
    return _OP_NORMALIZE.get(raw_op.strip(), "eq")


def _build_comparison_recall(current_op: str) -> list[str]:
    """构建运算符候选列表，当前 op 排第一。"""
    result = [current_op]
    for op in _ALL_COMPARISON_OPS:
        if op != current_op:
            result.append(op)
    return result


def _restore_clarify_to_confirmed(
    confirmed: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
) -> None:
    """将 clarify_items 按 path 还原回 confirmed 的各列表。

    LLM 可能把不确定的术语从 select/filters/order_by 中移除，
    只放在 clarify_items 里。这导致 confirmed 列表和 original 列表长度不一致。
    此函数按 clarify_item.path 解析出位置，将占位符插回对应列表，
    使 confirmed 列表和 original 列表长度一致，zip 配对不截断。
    """
    if not confirmed.clarify_items:
        return

    # 收集需要插入的位置：(target_list_name, index, keyword)
    inserts: dict[str, list[tuple[int, str]]] = {}
    for ci in confirmed.clarify_items:
        path = ci.path.strip("/")
        parts = path.split("/")
        if len(parts) < 2:
            continue
        list_name = parts[0]
        try:
            idx = int(parts[1])
        except ValueError:
            continue
        inserts.setdefault(list_name, []).append((idx, ci.keyword))

    # 按 index 降序插入（从后往前，避免索引偏移）
    for list_name, items in inserts.items():
        items.sort(key=lambda x: x[0], reverse=True)
        target: list[Any] | None = None
        if list_name == "select" and isinstance(confirmed, ConfirmedStructuredQuery):
            target = confirmed.select
        elif list_name == "dimensions" and isinstance(confirmed, ConfirmedStructuredCompute):
            target = confirmed.dimensions
        elif list_name == "filters":
            target = confirmed.filters
        elif list_name == "order_by":
            target = confirmed.order_by
        if target is None:
            continue
        for idx, keyword in items:
            # 用占位符标记：这个位置需要澄清，keyword 是原始术语
            # filters/order_by 是 list[dict]，需要用 dict 占位符
            if list_name in ("filters", "order_by"):
                placeholder: Any = {"__clarify__": keyword}
            else:
                placeholder = f"__clarify__{keyword}"
            if idx <= len(target):
                target.insert(idx, placeholder)
            else:
                target.append(placeholder)


# 合法运算符候选（与 WhereClause.op 一致）
_ALL_COMPARISON_OPS: list[str] = ["eq", "gt", "lt", "gte", "lte", "in", "between"]


def _build_comparison_recall(current_op: str) -> list[str]:
    """构建运算符候选列表，当前 op 排第一。"""
    result = [current_op]
    for op in _ALL_COMPARISON_OPS:
        if op != current_op:
            result.append(op)
    return result


def _fix_term_positions(
    sentence: str,
    mappings: list[ConditionTermMapping],
) -> None:
    """校正 LLM 返回的 start/end 位置。

    策略：
    - 术语在句子中只出现一次 → 直接 str.find，忽略 LLM 给的位置（LLM 偏差可能很大）
    - 术语出现多次 → 以 LLM start 为锚点 ±RADIUS 搜索，用位置消歧
    """
    used_positions: set[int] = set()
    for tm in mappings:
        term = tm.original_term
        term_len = len(term)
        best_pos: int | None = None

        # 统计术语在句子中出现的所有位置
        occurrences: list[int] = []
        search_start = 0
        while True:
            idx = sentence.find(term, search_start)
            if idx == -1:
                break
            occurrences.append(idx)
            search_start = idx + 1

        if len(occurrences) == 1:
            # 唯一出现 → 直接采信，不看 LLM 位置
            best_pos = occurrences[0]
        elif len(occurrences) > 1:
            # 多次出现 → 以 LLM start 为锚点，选最近且未占用的
            for occ in sorted(occurrences, key=lambda p: abs(p - tm.start)):
                if occ not in used_positions:
                    best_pos = occ
                    break
        # occurrences 为空 → best_pos 保持 None（术语不在句子中）

        if best_pos is not None and (best_pos != tm.start or best_pos + term_len != tm.end):
            logger.debug(
                "[cartesian] 位置校正: '%s' (%d,%d) → (%d,%d)",
                term,
                tm.start,
                tm.end,
                best_pos,
                best_pos + term_len,
            )
            tm.start = best_pos
            tm.end = best_pos + term_len
            used_positions.add(best_pos)
        else:
            used_positions.add(tm.start)


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

    # 校正 LLM 返回的 start/end（LLM 数字符位置常有 ±1~2 偏差）
    _fix_term_positions(sentence, confirmed_mappings)
    _fix_term_positions(sentence, unconfirmed_mappings)

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
    original_structured: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], KnowledgeMeta]:
    """基于 LLM 确认结果构建 paradigmList + 内部元数据。

    设计原则：
        LLM confirm 的输出是唯一数据源。paradigmList 完全反映 LLM 的判断：
        - 已确认的字段（confirmed 结构中已替换为真实字段名）→ 单候选自动选中
        - 待澄清的字段（clarify_items）→ 展示 LLM 精选的候选列表让用户选
        - complex_conditions（confirmed_conditions）→ 笛卡尔积展开到过滤条件

        terms 和 recall_map 不参与候选列表构建，仅用于：
        - terms: 提供 path_mapping（JSON pointer），供 format 阶段精确回写
        - recall_map: 不再使用（保留参数签名以兼容调用方）

    Args:
        confirmed: LLM 确认后的完整结构。
        terms: 提取的术语列表（仅用于 path 查找）。
        recall_map: 召回结果（不再使用，保留兼容）。
        complex_conditions: 原始 complex_conditions 列表。
        original_structured: 原始 StructuredQuery/StructuredCompute dict，用于读取 op 等元信息。

    Returns:
        (paradigmList, KnowledgeMeta) 元组。
    """
    mode = "query" if isinstance(confirmed, ConfirmedStructuredQuery) else "compute"
    path_mapping: dict[str, str] = {}
    _orig = original_structured or {}

    # ── 将 clarify_items 按 path 还原回 confirmed 列表 ──
    _restore_clarify_to_confirmed(confirmed)

    # ── 构建 path 查找索引：raw_text+ktype → path ──
    # terms 的唯一作用是提供 JSON pointer，供 format 阶段回写用户选择。
    _path_index: dict[tuple[str, str], str] = {}
    for t in terms:
        if t.source == "main":
            key = (t.raw_text, t.ktype)
            if key not in _path_index:
                _path_index[key] = t.path

    def _find_path(keyword: str, ktype: str, fallback: str = "") -> str:
        return _path_index.get((keyword, ktype), fallback)

    # ── clarify_items 按 keyword 索引（快速查找某术语是否需要澄清）──
    clarify_map: dict[str, ClarifyItem] = {}
    for ci in confirmed.clarify_items:
        clarify_map[ci.keyword] = ci

    # ── paradigmId=1: 查询值 ──
    # 数据源：ConfirmedStructuredQuery.select / ConfirmedStructuredCompute.dimensions
    select_result: list[dict[str, Any]] = []
    if isinstance(confirmed, ConfirmedStructuredQuery):
        original_select = [t.raw_text for t in terms if t.ktype == "select" and t.source == "main"]
        confirmed_select = confirmed.select
        for kid, (orig, conf) in enumerate(
            zip(original_select, confirmed_select, strict=False), start=1
        ):
            if orig in clarify_map:
                # LLM 认为不确定 → 展示候选让用户选
                ci = clarify_map[orig]
                item: dict[str, Any] = {
                    "keyword": orig,
                    "recall": ci.candidates,
                    "kid": kid,
                    "ktype": "select",
                }
            else:
                # LLM 已确认 → 单候选自动选中
                item = {
                    "keyword": orig,
                    "recall": [conf],
                    "kid": kid,
                    "ktype": "select",
                    "choiceKeyword": conf,
                }
            path_mapping[str(kid)] = _find_path(orig, "select", f"select.{kid - 1}")
            select_result.append(item)

    # ── paradigmId=2: 分组条件 ──
    group_result: list[dict[str, Any]] = []
    if isinstance(confirmed, ConfirmedStructuredCompute):
        original_dims = [t.raw_text for t in terms if t.ktype == "groupBy" and t.source == "main"]
        confirmed_dims = [
            str(d.get("field", "")) if isinstance(d, dict) else str(d) for d in confirmed.dimensions
        ]
        for i, (orig, conf) in enumerate(zip(original_dims, confirmed_dims, strict=False)):
            if orig in clarify_map:
                ci = clarify_map[orig]
                item = {
                    "keyword": orig,
                    "recall": ci.candidates,
                    "kid": i + 1,
                    "ktype": "groupBy",
                }
            else:
                item = {
                    "keyword": orig,
                    "recall": [conf],
                    "kid": i + 1,
                    "ktype": "groupBy",
                    "choiceKeyword": conf,
                }
            path_mapping[f"g{i + 1}"] = _find_path(orig, "groupBy", f"dimensions.{i}")
            group_result.append(item)

    # ── paradigmId=3: 过滤条件 ──
    filter_result: list[dict[str, Any]] = []
    # 主结构 filters：对比原始 vs LLM 确认
    original_filters = [
        t for t in terms if t.ktype in ("whereKey", "whereValue") and t.source == "main"
    ]
    # 按 path 前缀配对 key+value
    _build_filter_paradigm_from_confirmed(
        confirmed.filters,
        original_filters,
        clarify_map,
        filter_result,
        path_mapping,
        original_filters_raw=list(_orig.get("filters") or []),
    )
    # complex_conditions → 笛卡尔积展开
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

    # ── paradigmId=4: 排序目标 ──
    order_result: list[dict[str, Any]] = []
    original_order = [t.raw_text for t in terms if t.ktype == "orderBy" and t.source == "main"]
    confirmed_order = [
        str(o.get("field", "")) if isinstance(o, dict) else str(o) for o in confirmed.order_by
    ]
    for i, (orig, conf) in enumerate(zip(original_order, confirmed_order, strict=False)):
        if orig in clarify_map:
            ci = clarify_map[orig]
            item = {
                "keyword": orig,
                "recall": ci.candidates,
                "kid": i + 1,
                "ktype": "orderBy",
            }
        else:
            item = {
                "keyword": orig,
                "recall": [conf],
                "kid": i + 1,
                "ktype": "orderBy",
                "choiceKeyword": conf,
            }
        path_mapping[f"o{i + 1}"] = _find_path(orig, "orderBy", f"order_by.{i}.field")
        order_result.append(item)

    # ── paradigmId=5: 统计函数（空）──
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


def _build_filter_paradigm_from_confirmed(
    confirmed_filters: list[dict[str, Any]],
    original_filter_terms: list[ExtractedTerm],
    clarify_map: dict[str, ClarifyItem],
    filter_result: list[dict[str, Any]],
    path_mapping: dict[str, str],
    original_filters_raw: list[dict[str, Any]] | None = None,
) -> None:
    """基于 LLM 确认的 filters 构建过滤条件 paradigm。

    对比原始 filter terms 和 LLM 确认后的 filters，
    已确认的自动选中，待澄清的展示候选。
    """
    _orig_filters = original_filters_raw or []
    # 按 path 前缀配对原始 whereKey + whereValue
    key_terms = [t for t in original_filter_terms if t.ktype == "whereKey"]
    value_terms = [t for t in original_filter_terms if t.ktype == "whereValue"]

    paired: dict[str, dict[str, ExtractedTerm]] = {}
    for t in key_terms:
        parts = t.path.rsplit(".", 1)
        prefix = parts[0] if len(parts) > 1 else t.path
        paired.setdefault(prefix, {})["key"] = t
    for t in value_terms:
        parts = t.path.rsplit(".", 1)
        prefix = parts[0] if len(parts) > 1 else t.path
        paired.setdefault(prefix, {})["value"] = t

    for idx, (prefix, pair) in enumerate(sorted(paired.items())):
        key_term = pair.get("key")
        value_term = pair.get("value")
        if key_term is None:
            continue

        # 从 LLM confirmed_filters 中找对应的确认结果
        conf_filter = confirmed_filters[idx] if idx < len(confirmed_filters) else {}
        conf_field = str(conf_filter.get("field", ""))

        # comparison：优先 LLM 确认结果，其次原始 structured_query，兜底 "eq"
        orig_filter = _orig_filters[idx] if idx < len(_orig_filters) else {}
        raw_op = str(
            conf_filter.get("op", "")
            or conf_filter.get("comparison", "")
            or orig_filter.get("op", "")
            or "eq"
        )
        comparison = _normalize_op(raw_op)

        item: dict[str, Any] = {
            "field": key_term.raw_text,
            "comparison": comparison,
            "comparisonRecall": _build_comparison_recall(comparison),
            "choiceComparison": comparison,
        }

        # field 部分
        if key_term.raw_text in clarify_map:
            ci = clarify_map[key_term.raw_text]
            item["fieldRecall"] = ci.candidates
        else:
            item["fieldRecall"] = [conf_field] if conf_field else []
            if conf_field:
                item["choiceField"] = conf_field

        # value 部分
        if value_term:
            conf_values = conf_filter.get("value", "")
            item["value"] = value_term.raw_text
            if value_term.raw_text in clarify_map:
                ci = clarify_map[value_term.raw_text]
                item["valueRecall"] = ci.candidates
            else:
                val_list = conf_values if isinstance(conf_values, list) else [conf_values]
                item["valueRecall"] = [str(v) for v in val_list if v]
                if len(item["valueRecall"]) == 1:
                    item["choiceValue"] = item["valueRecall"][0]
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
