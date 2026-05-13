"""Structured input patching — backfill confirmed fields into structured dicts.

Moved from api.py to keep the orchestrator lean.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from ._pre_resolve import term_key
from .models import ExtractedTerm, PreResolveResult


def build_pre_resolved_input(
    structured_input: dict[str, Any],
    pre_resolve: PreResolveResult,
    main_terms: list[ExtractedTerm],
) -> dict[str, Any]:
    """将已确认字段替换到 structured_input 中（用中文 term_name）。"""
    result = json.loads(json.dumps(structured_input, ensure_ascii=False))

    # 非 whereValue 字段直接替换
    for t in main_terms:
        if t.source != "main" or term_key(t) not in pre_resolve.confirmed:
            continue
        if t.ktype == "whereValue":
            continue
        rf = pre_resolve.confirmed[term_key(t)]
        _set_by_path(result, t.path, rf.term_name)

    # whereValue 列表感知替换
    _apply_confirmed_values(result, main_terms, pre_resolve.confirmed)

    # 移除 complex_conditions（主结构不需要）
    result.pop("complex_conditions", None)
    return result


def set_by_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """按 JSON pointer 路径设置值。"""
    parts = path.split(".")
    current: Any = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return
        else:
            return
    if current is None:
        return
    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        with contextlib.suppress(ValueError, IndexError):
            current[int(last)] = value


def apply_value_list(
    obj: dict[str, Any],
    value_path: str,
    idx_vals: list[tuple[int, str]],
) -> None:
    """按索引替换 filter value 列表中的元素（不覆盖整个列表）。

    Args:
        obj: 结构化输入。
        value_path: 如 'filters.0.value'。
        idx_vals: [(列表内索引, 确认值)] 列表。
    """
    parts = value_path.split(".")
    current: Any = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return
        else:
            return
        if current is None:
            return

    if isinstance(current, list):
        for idx, val in idx_vals:
            if 0 <= idx < len(current):
                current[idx] = val
    elif idx_vals:
        set_by_path(obj, value_path, idx_vals[-1][1])


def apply_confirmed_values(
    obj: dict[str, Any],
    main_terms: list[ExtractedTerm],
    confirmed: dict[str, Any],
    *,
    term_source: str = "",
) -> None:
    """批量回填已确认的 whereValue 到 filter value 列表。"""
    # 按 value path 分组
    by_path: dict[str, list[tuple[int, str]]] = {}
    path_counters: dict[str, int] = {}
    for t in main_terms:
        if t.source != "main" or t.ktype != "whereValue":
            continue
        tk = term_key(t)
        if tk not in confirmed:
            continue
        rf = confirmed[tk]
        idx = path_counters.get(t.path, 0)
        path_counters[t.path] = idx + 1
        term_name = rf.term_name if hasattr(rf, "term_name") else str(rf)
        by_path.setdefault(t.path, []).append((idx, term_name))

    for vpath, idx_vals in by_path.items():
        apply_value_list(obj, vpath, idx_vals)


# backward compat aliases (used in api.py)
_build_pre_resolved_input = build_pre_resolved_input
_set_by_path = set_by_path
_apply_value_list = apply_value_list
_apply_confirmed_values = apply_confirmed_values
