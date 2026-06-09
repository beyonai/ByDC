"""Layer 2 — 字段消歧。

通过 _patterns.query_scope_props 获取 scope 下的所有属性术语，
然后客户端 termName/别名 精确匹配，返回结构化消歧结果。
"""

from __future__ import annotations

import logging

from datacloud_knowledge.capabilities.protocol import TermStore
from datacloud_knowledge.contracts.types import (
    AmbiguousCandidate,
    FieldResolutionResult,
)

from ._patterns import query_scope_props

log = logging.getLogger(__name__)

__all__ = ["resolve_field_aliases"]


def resolve_field_aliases(
    store: TermStore,
    *,
    terms: list[str],
    scope_code: str,
) -> FieldResolutionResult:
    """字段别名精确消歧：在 scope 下查找字段别名 → prop term_code。

    流程：
    1. _patterns.query_scope_props(store, scope_code) 获取 scope 下所有 prop
    2. 对每个输入项，用 term_name + | 分隔的 synonyms 精确匹配
    3. 无歧义单命中 → resolved；多命中 → ambiguous；零命中 → unresolved

    Args:
        store:      TermStore 实例。
        terms:      待解析的字段名称/别名列表（如 ``["销售额", "客户名"]``）。
        scope_code: scope 术语编码（如 ``"scene_enterprise_analysis"``）。

    Returns:
        FieldResolutionResult。
    """
    result = query_scope_props(store, scope_code)

    # 对每个 prop 预解析其别名
    prop_aliases: list[tuple[str, str, str, list[str]]] = []
    # (term_code, term_name, |delimited_synonyms, [alias_list])
    for prop in result.items:
        alias_list: list[str] = []
        if prop.synonyms:
            alias_list = [s.strip() for s in prop.synonyms.split("|") if s.strip()]
        prop_aliases.append((prop.term_code, prop.term_name, prop.synonyms, alias_list))

    resolved: dict[str, str] = {}
    ambiguous: dict[str, list[AmbiguousCandidate]] = {}
    unresolved: list[str] = []

    for term in terms:
        normalized = term.strip()
        matches: list[AmbiguousCandidate] = []

        for term_code, term_name, _syn_str, aliases in prop_aliases:
            # 匹配 term_name
            if normalized == term_name:
                matches.append(
                    AmbiguousCandidate(
                        term_code=term_code,
                        term_name=term_name,
                        matched_alias=normalized,
                        scope={"scope": scope_code},
                    )
                )
                continue

            # 匹配 | 分隔的别名
            for alias in aliases:
                if normalized == alias:
                    matches.append(
                        AmbiguousCandidate(
                            term_code=term_code,
                            term_name=term_name,
                            matched_alias=normalized,
                            scope={"scope": scope_code},
                        )
                    )
                    break  # 同一 prop 只记一次

        if len(matches) == 1:
            # 无歧义 — 按 term_code 取第一个
            resolved[normalized] = matches[0].term_code
        elif len(matches) > 1:
            ambiguous[normalized] = matches
        else:
            unresolved.append(normalized)

    return FieldResolutionResult(
        resolved=resolved,
        ambiguous=ambiguous,
        unresolved=unresolved,
    )
