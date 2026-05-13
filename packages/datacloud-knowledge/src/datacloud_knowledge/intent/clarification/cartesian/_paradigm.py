"""paradigmList building — build the front-end paradigmList payload from confirmed results.

Builds the five paradigm groups (query values, groups, filters, order, aggregates)
from LLM-confirmed structured results, performing Cartesian expansion on
complex_conditions and collecting path mappings for the format stage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_knowledge.i18n import get_paradigm_labels
from datacloud_knowledge.intent.clarification.models import (
    ClarifyItem,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    KnowledgeMeta,
)

from ._expand import _build_comparison_recall, _normalize_op, expand_condition_cartesian

logger = logging.getLogger(__name__)


def build_paradigm_list(
    confirmed: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    *,
    language: str = "zh_CN",
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

    # ── clarify_items 按 keyword 索引（支持同名术语多次出现）──
    clarify_map: dict[str, list[ClarifyItem]] = {}
    for ci in confirmed.clarify_items:
        clarify_map.setdefault(ci.keyword, []).append(ci)

    def _pop_clarify(keyword: str) -> ClarifyItem | None:
        """从 clarify_map 中取出一个匹配的 ClarifyItem（先进先出）。"""
        items = clarify_map.get(keyword)
        if not items:
            return None
        ci = items.pop(0)
        if not items:
            del clarify_map[keyword]
        return ci

    # ── paradigmId=1: 查询值 ──
    # 数据源：ConfirmedStructuredQuery.select / ConfirmedStructuredCompute.dimensions
    select_result: list[dict[str, Any]] = []
    if isinstance(confirmed, ConfirmedStructuredQuery):
        original_select = [t.raw_text for t in terms if t.ktype == "select" and t.source == "main"]
        confirmed_select = confirmed.select
        for kid, (orig, conf) in enumerate(
            zip(original_select, confirmed_select, strict=False), start=1
        ):
            ci = _pop_clarify(orig)
            if ci is not None:
                # LLM 认为不确定 → 展示候选让用户选
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
    elif isinstance(confirmed, ConfirmedStructuredCompute):
        # compute 模式：metrics 中的字段也作为查询值展示
        original_metrics = [t.raw_text for t in terms if t.ktype == "select" and t.source == "main"]
        confirmed_metrics_raw = confirmed.metrics
        confirmed_metric_fields = [
            str(m.get("field", "")) if isinstance(m, dict) else str(m)
            for m in confirmed_metrics_raw
        ]
        for kid, (orig, conf) in enumerate(
            zip(original_metrics, confirmed_metric_fields, strict=False), start=1
        ):
            ci = _pop_clarify(orig)
            if ci is not None:
                item = {
                    "keyword": orig,
                    "recall": ci.candidates,
                    "kid": kid,
                    "ktype": "select",
                }
            else:
                item = {
                    "keyword": orig,
                    "recall": [conf],
                    "kid": kid,
                    "ktype": "select",
                    "choiceKeyword": conf,
                }
            path_mapping[str(kid)] = _find_path(orig, "select", f"metrics.{kid - 1}.field")
            select_result.append(item)

    # ── paradigmId=2: 分组条件 ──
    group_result: list[dict[str, Any]] = []
    if isinstance(confirmed, ConfirmedStructuredCompute):
        original_dims = [t.raw_text for t in terms if t.ktype == "groupBy" and t.source == "main"]
        confirmed_dims = [
            str(d.get("field", "")) if isinstance(d, dict) else str(d) for d in confirmed.dimensions
        ]
        for i, (orig, conf) in enumerate(zip(original_dims, confirmed_dims, strict=False)):
            ci = _pop_clarify(orig)
            if ci is not None:
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
            expanded = expand_condition_cartesian(cc, language=language)
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
        ci = _pop_clarify(orig)
        if ci is not None:
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

    p_labels = get_paradigm_labels(language)

    paradigm_list = [
        {
            "paradigmId": "1",
            "paradigmName": p_labels["1"],
            "paradigmResult": select_result,
        },
        {
            "paradigmId": "2",
            "paradigmName": p_labels["2"],
            "paradigmResult": group_result,
        },
        {
            "paradigmId": "3",
            "paradigmName": p_labels["3"],
            "paradigmResult": filter_result,
        },
        {
            "paradigmId": "4",
            "paradigmName": p_labels["4"],
            "paradigmResult": order_result,
        },
        {
            "paradigmId": "5",
            "paradigmName": p_labels["5"],
            "paradigmResult": agg_result,
        },
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
    clarify_map: dict[str, list[ClarifyItem]],
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
        field_items = clarify_map.get(key_term.raw_text)
        if field_items:
            ci = field_items.pop(0)
            if not field_items:
                del clarify_map[key_term.raw_text]
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
                val_items = clarify_map[value_term.raw_text]
                ci = val_items.pop(0)
                if not val_items:
                    del clarify_map[value_term.raw_text]
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
