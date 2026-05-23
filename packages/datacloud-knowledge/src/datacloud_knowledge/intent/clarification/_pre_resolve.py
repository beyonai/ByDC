"""Pre-resolve — deterministic field alias resolution before LLM confirmation.

Moved from api.py to eliminate local imports and enable independent testing.
"""

from __future__ import annotations

import logging

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.intent_types import (
    find_paired_where_key,
    is_field_code,
    term_key,
)
from datacloud_knowledge.contracts.types import ResolvedField

from .models import ExtractedTerm, PreResolveResult

logger = logging.getLogger(__name__)


def pre_resolve_terms(
    terms: list[ExtractedTerm],
    scope_code: str,
) -> PreResolveResult:
    """Phase 2: 预解析可确定匹配的术语。

    - 英文 field_code / 中文唯一精确命中 → confirmed_exact
    - 歧义 / 未命中 → unresolved，走 recall
    - 已确认 whereKey → 查 prop 枚举值约束 whereValue

    Args:
        terms: 从主结构或 complex_conditions 提取的术语列表。
        scope_code: 本体编码。

    Returns:
        PreResolveResult。
    """
    confirmed: dict[str, ResolvedField] = {}  # keyed by path
    provenance: dict[str, str] = {}  # keyed by path
    value_enum_map: dict[str, list[str]] = {}  # keyed by path

    # 收集字段类术语（非 whereValue），去重 raw_text 用于 SQL 查询
    field_terms_raw: list[str] = []
    for t in terms:
        if not t.search_enabled:
            continue
        if t.ktype == "whereValue" or t.parent_raw_text is not None:
            continue
        if t.raw_text not in field_terms_raw:
            field_terms_raw.append(t.raw_text)

    # 调用扩展版别名解析（返回 {raw_text → ResolvedField}）
    resolved_by_text: dict[str, ResolvedField] = {}
    if field_terms_raw and scope_code:
        try:
            result = create_reader().resolve_field_aliases_with_names(
                terms=field_terms_raw,
                scope_code=scope_code,
            )
            resolved_by_text = result.resolved
            # 扇出到所有匹配的术语，按 path:raw_text 复合键入
            for t in terms:
                if t.ktype == "whereValue" or t.parent_raw_text is not None:
                    continue
                rf = resolved_by_text.get(t.raw_text)
                if rf:
                    tk = term_key(t)
                    confirmed[tk] = rf
                    tag = "field_code" if is_field_code(t.raw_text) else "alias_exact"
                    provenance[tk] = tag
            logger.info(
                "[pre_resolve] resolved=%d ambiguous=%d unresolved=%d",
                len(result.resolved),
                len(result.ambiguous),
                len(result.unresolved),
            )
        except Exception:
            logger.warning("[pre_resolve] resolve_field_aliases_with_names 失败", exc_info=True)

    # 已确认 whereKey → 查枚举值
    confirmed_key_codes: list[str] = []
    key_code_to_name: dict[str, str] = {}
    for t in terms:
        if t.ktype == "whereKey" and term_key(t) in confirmed:
            rf = confirmed[term_key(t)]
            if rf.term_code not in key_code_to_name:
                confirmed_key_codes.append(rf.term_code)
                key_code_to_name[rf.term_code] = rf.term_name

    if confirmed_key_codes and scope_code:
        try:
            enum_map = create_reader().get_prop_enum_values(
                scope_code=scope_code,
                field_codes=confirmed_key_codes,
            )
            # 为每个 whereValue 术语建立枚举约束（按 path 键入）
            for t in terms:
                if t.ktype != "whereValue" or not t.search_enabled:
                    continue
                key_term = find_paired_where_key(t, terms)
                if key_term and term_key(key_term) in confirmed:
                    rf = confirmed[term_key(key_term)]
                    enum_values = enum_map.get(rf.term_code, [])
                    if enum_values:
                        tk = term_key(t)
                        value_enum_map[tk] = enum_values
                        # 尝试在枚举集内精确匹配
                        for ev in enum_values:
                            if ev == t.raw_text:
                                confirmed[tk] = ResolvedField(
                                    term_code=ev,
                                    term_name=ev,
                                )
                                provenance[tk] = "enum_exact"
                                break
        except Exception:
            logger.warning("[pre_resolve] get_prop_enum_values 失败", exc_info=True)

    # 查询 ontology 下所有 prop→type 绑定，供召回层按 type_code 过滤
    prop_type_map: dict[str, str] = {}
    if scope_code:
        try:
            prop_type_map = create_reader().get_prop_type_map(
                scope_code=scope_code,
                field_codes=None,  # 拉全量，覆盖所有 prop
            )
            logger.info(
                "[pre_resolve] prop_type_map loaded: %d props with HAS_TERM",
                len(prop_type_map),
            )
        except Exception:
            logger.warning("[pre_resolve] get_prop_type_map 失败", exc_info=True)

    # 分拣 unresolved
    unresolved: list[ExtractedTerm] = []
    for t in terms:
        if term_key(t) in confirmed:
            continue
        unresolved.append(t)

    logger.info(
        "[pre_resolve] confirmed=%d unresolved=%d value_constraints=%d",
        len(confirmed),
        len(unresolved),
        len(value_enum_map),
    )

    return PreResolveResult(
        confirmed=confirmed,
        unresolved_terms=unresolved,
        value_enum_map=value_enum_map,
        provenance=provenance,
        prop_type_map=prop_type_map,
    )
