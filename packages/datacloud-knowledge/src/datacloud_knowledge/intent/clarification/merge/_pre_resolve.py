"""Pre-resolve merge — backfill deterministically resolved fields into result dict.

Extracted from merge_confirmed_common so the pre-resolve backfill step is
independently testable and the main merge function stays focused.
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.intent.clarification._patch import apply_confirmed_values, set_by_path
from datacloud_knowledge.intent.clarification._pre_resolve import term_key
from datacloud_knowledge.intent.clarification.models import ExtractedTerm, PreResolveResult


def apply_pre_resolve_results(
    result: dict[str, Any],
    main_terms: list[ExtractedTerm],
    pre: PreResolveResult,
) -> None:
    """回填 pre_resolve 已确认字段到结果 dict（就地修改）。

    - 非 whereValue 字段直接 set_by_path。
    - whereValue 字段用列表感知的 apply_confirmed_values 回填。
    """
    for t in main_terms:
        if t.source != "main" or term_key(t) not in pre.confirmed:
            continue
        if t.ktype == "whereValue":
            continue  # whereValue 列表需要特殊处理
        rf = pre.confirmed[term_key(t)]
        set_by_path(result, t.path, rf.term_name)

    # 列表感知回填 whereValue
    apply_confirmed_values(result, main_terms, pre.confirmed, term_source="pre_resolve")
