"""Layer 2 — 枚举值查询。

通过 _patterns.query_scope_props 获取 scope 下所有 prop，
提取 termBinding 编码后用 _patterns.query_bound_values 批量获取值术语。
"""

from __future__ import annotations

import json
import logging

from datacloud_knowledge.capabilities.protocol import TermStore

from ._patterns import query_bound_values, query_scope_props

log = logging.getLogger(__name__)

__all__ = ["get_prop_enum_values"]


def get_prop_enum_values(
    store: TermStore,
    *,
    scope_code: str,
    field_codes: list[str],
) -> dict[str, list[str]]:
    """查询指定 prop 的枚举值。

    路径::

        view/object(scope_code) → (HAS_FIELD) → prop(field_code) → child terms

    流程：
    1. _patterns.query_scope_props → 获取 scope 下所有 prop 的 termBinding
    2. 提取 prop.term_code 匹配 field_codes，收集 termBinding value 编码
    3. _patterns.query_bound_values → 批量获取值术语的 term_name + 别名

    Args:
        store:       TermStore 实例。
        scope_code:  scope 术语编码（如 ``"scene_enterprise_analysis"``）。
        field_codes: 待查询的 prop term_code 列表。

    Returns:
        {field_code → [枚举值列表]}，去重保序。
    """
    if not field_codes:
        return {}

    # Step 1: 获取 scope 下所有 prop
    result = query_scope_props(store, scope_code)
    props = result.items

    # 提取 termBinding: prop term_code → [value term_code, ...]
    binding_map: dict[str, list[str]] = {}
    for prop in props:
        if prop.term_code not in field_codes:
            continue
        binding_codes = _extract_binding_codes(prop.ext_attrs)
        if binding_codes:
            binding_map[prop.term_code] = binding_codes

    if not binding_map:
        return {fc: [] for fc in field_codes}

    # Step 2: 收集所有 binding value 编码
    all_binding_codes: list[str] = []
    code_to_prop: dict[str, str] = {}  # value_code → prop_term_code
    for prop_code, bcs in binding_map.items():
        for bc in bcs:
            all_binding_codes.append(bc)
            code_to_prop[bc] = prop_code

    # Step 3: 批量查询值术语
    value_result = query_bound_values(store, all_binding_codes)

    # Step 4: 构建结果
    enum_map: dict[str, dict[str, None]] = {fc: {} for fc in field_codes}
    for val in value_result.items:
        pcode = code_to_prop.get(val.term_code)
        if pcode is None:
            continue
        entry = enum_map.setdefault(pcode, {})
        entry[val.term_name] = None
        # 别名
        if val.synonyms:
            for raw_alias in val.synonyms.split("|"):
                a = raw_alias.strip()
                if a:
                    entry[a] = None

    return {fc: list(enum_map.get(fc, {}).keys()) for fc in field_codes}


def _extract_binding_codes(ext_attrs: dict[str, str]) -> list[str]:
    """从 ext_attrs 中提取 termBinding 值编码。

    ext_attrs["termBinding"] 是 JSON 字符串或管道分隔或逗号分隔。
    """
    raw = ext_attrs.get("termBinding", "")
    if not raw:
        return []
    # 尝试 JSON 解析
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        if isinstance(parsed, dict):
            codes = parsed.get("value_term_codes") or parsed.get("valueCodes") or []
            if isinstance(codes, list):
                return [str(c) for c in codes if c]
        return []
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试管道/逗号分隔
    return [s.strip() for s in raw.replace("|", ",").split(",") if s.strip()]
