"""字段分析能力规则引擎。

根据 OWL ext_property.property_role_rule 派生字段的 filter_ops / group_ops / aggregate_ops。
"""

from __future__ import annotations

import html
import json
from typing import Any


# ── OWL property_role → 运行时 analytic_role ──────────────────────────────────
_ROLE_MAP: dict[str, str] = {
    "DIMENSION_ATTR": "dimension",
    "MEASURE": "measure",
}

# ── OWL rule_type → 运行时 analytic_kind ─────────────────────────────────────
_KIND_MAP: dict[str, str] = {
    "id": "id",
    "name": "name",
    "time": "time",
    "period": "period",
    "numerical": "number",  # OWL numerical → 运行时 number
    "index_numerical": "number",  # OWL index_numerical → 运行时 number
    "indicator": "indicator",
}

# ── 默认操作符映射 (analytic_role, analytic_kind) → ops ───────────────────────
_FILTER_OPS: dict[tuple[str, str], list[str]] = {
    ("dimension", "id"): ["eq", "in", "is_null", "is_not_null"],
    ("dimension", "name"): ["eq", "in", "like", "is_null", "is_not_null"],
    ("dimension", "time"): [
        "eq",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "is_null",
        "is_not_null",
    ],
    ("dimension", "period"): [
        "eq",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "is_null",
        "is_not_null",
    ],
    ("dimension", "number"): ["eq", "in", "gt", "gte", "lt", "lte", "is_null", "is_not_null"],
    ("measure", "id"): ["eq", "in", "is_null", "is_not_null"],
    ("measure", "number"): ["eq", "in", "gt", "gte", "lt", "lte", "is_null", "is_not_null"],
    ("measure", "indicator"): ["eq", "in", "gt", "gte", "lt", "lte", "is_null", "is_not_null"],
}

_GROUP_OPS: dict[tuple[str, str], list[str]] = {
    ("dimension", "id"): ["self"],
    ("dimension", "name"): ["self"],
    ("dimension", "time"): ["day", "month", "quarter", "year"],
    ("dimension", "period"): ["month", "quarter", "year"],
    ("dimension", "number"): [],  # 数值维度不允许分组
    ("measure", "id"): ["self"],
    ("measure", "number"): ["range"],
    ("measure", "indicator"): ["range"],
}

_AGG_OPS: dict[tuple[str, str], list[str]] = {
    ("dimension", "id"): ["count", "count_distinct"],
    ("dimension", "name"): [],
    ("dimension", "time"): [],
    ("dimension", "period"): [],
    ("dimension", "number"): ["sum", "avg", "min", "max"],
    ("measure", "id"): ["count", "count_distinct"],
    ("measure", "number"): ["sum", "avg", "min", "max"],
    ("measure", "indicator"): ["sum", "count", "count_distinct", "avg", "min", "max"],
}

# ── 强制过滤组 ────────────────────────────────────────────────────────────────
_REQUIRED_FILTER_GROUP: dict[tuple[str, str], str] = {
    ("dimension", "period"): "period_required",
}


def parse_analytic_role(ext_property_json: str | None) -> tuple[str | None, str | None]:
    """
    从 OWL ext_property JSON 字符串提取运行时分析角色。

    Returns:
        (analytic_role, analytic_kind) - 均可能为 None
    """
    if not ext_property_json:
        return None, None
    try:
        data = json.loads(html.unescape(ext_property_json))
    except (ValueError, TypeError):
        return None, None
    rule = data.get("property_role_rule", {})
    property_role = rule.get("property_role", "")
    rule_type = rule.get("rule_type", "")
    return _ROLE_MAP.get(property_role), _KIND_MAP.get(rule_type)


def derive_field_ops(
    analytic_role: str | None,
    analytic_kind: str | None,
    has_term: bool = False,
    term_type: str | None = None,
) -> tuple[list[str], list[str], list[str], str | None]:
    """
    根据分析角色和细分类型派生操作符集合。

    Args:
        analytic_role: "dimension" | "measure"
        analytic_kind: "id" | "name" | "time" | "period" | "number" | "indicator"
        has_term: 是否绑定术语词库（已废弃，由 term_type 替代，保留向后兼容）
        term_type: "enum" | "lookup" | None — 只有 enum 型才收敛 filter_ops

    Returns:
        (filter_ops, group_ops, aggregate_ops, required_filter_group)
    """
    if not analytic_role or not analytic_kind:
        # 兼容：无分析角色时按字段类型给最小操作符
        return ["eq", "in", "is_null", "is_not_null"], [], [], None

    key = (analytic_role, analytic_kind)
    filter_ops = list(_FILTER_OPS.get(key, ["eq", "in", "is_null", "is_not_null"]))
    group_ops = list(_GROUP_OPS.get(key, []))
    agg_ops = list(_AGG_OPS.get(key, []))
    required = _REQUIRED_FILTER_GROUP.get(key)

    # 仅枚举型术语绑定才收敛操作符（枚举值必须精确匹配，不支持 like/range）
    # lookup 型（文本翻译）保留全部 ops，like 依然有效
    is_enum_term = (term_type == "enum") or (has_term and term_type is None)
    if is_enum_term:
        filter_ops = [op for op in filter_ops if op in ("eq", "in", "is_null", "is_not_null")]

    return filter_ops, group_ops, agg_ops, required


def infer_secondary_role(analytic_role: str | None, analytic_kind: str | None) -> str | None:
    """
    规则引擎推断附加角色：
    - DIMENSION_ATTR + id → 附加 measure 能力（count/count_distinct）
    - DIMENSION_ATTR + number → 附加 measure 能力（sum/avg/max/min）
    """
    if analytic_role == "dimension" and analytic_kind in ("id", "number"):
        return "measure"
    return None


def apply_analytic_metadata(f: Any, ext_property_json: str | None = None) -> None:
    """
    将 OWL ext_property 解析结果写入 OntologyField。

    Args:
        f: OntologyField 实例
        ext_property_json: ext_property JSON 字符串（可从 OWL 直接传入）
    """
    role, kind = parse_analytic_role(ext_property_json)
    f.analytic_role = role
    f.analytic_kind = kind
    f.secondary_role = infer_secondary_role(role, kind)
    term_type = getattr(f, "term_type", None)
    f.filter_ops, f.group_ops, f.aggregate_ops, f.required_filter_group = derive_field_ops(
        role, kind, term_type=term_type
    )
