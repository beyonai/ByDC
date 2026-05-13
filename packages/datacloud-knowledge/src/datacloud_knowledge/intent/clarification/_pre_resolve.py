"""Pre-resolve — deterministic field alias resolution before LLM confirmation.

Moved from api.py to eliminate local imports and enable independent testing.
"""

from __future__ import annotations

import logging
import re

from datacloud_knowledge.search.term_search import (
    get_prop_enum_values,
    resolve_field_aliases_with_names,
)
from datacloud_knowledge.search.types import ResolvedField

from .models import ExtractedTerm, PreResolveResult

logger = logging.getLogger(__name__)

_FIELD_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_field_code(term: str) -> bool:
    """判断术语是否为英文字段编码。"""
    return bool(_FIELD_CODE_RE.match(term))


def term_key(t: ExtractedTerm) -> str:
    """生成术语的复合键：path:raw_text。"""
    return f"{t.path}:{t.raw_text}"


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
            result = resolve_field_aliases_with_names(
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
            enum_map = get_prop_enum_values(
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
    )


def find_paired_where_key(
    value_term: ExtractedTerm,
    all_terms: list[ExtractedTerm],
) -> ExtractedTerm | None:
    """查找 whereValue 对应的 whereKey 术语。"""
    filter_prefix = extract_filter_prefix(value_term.path)
    if not filter_prefix:
        return None
    for t in all_terms:
        if t.ktype == "whereKey" and extract_filter_prefix(t.path) == filter_prefix:
            return t
    return None


def extract_filter_prefix(path: str) -> str:
    """从 path 提取 filter 前缀：'filters.1.field' → 'filters.1'。

    支持 query 模式 (filters.*) 和 compute 模式 (metrics.*.filters.*)。
    """
    parts = path.split(".")
    if len(parts) >= 2 and parts[0] == "filters":
        return f"{parts[0]}.{parts[1]}"
    for i, p in enumerate(parts):
        if p in {"filters", "where"} and i + 1 < len(parts):
            try:
                int(parts[i + 1])
                return ".".join(parts[: i + 2])
            except ValueError:
                pass
    return ""
