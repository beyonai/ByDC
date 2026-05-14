"""CC normalization — complex_conditions result normalization and mapping dedup.

Normalizes per-condition confirmation results using cross-stage resolution
hints, and merges new confirmations back into the hints table.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.intent.clarification.models import (
    CCConfirmResult,
    CCTermConfirmation,
    CCTermMeta,
    ConditionTermMapping,
)

from ._hints import (
    _candidate_names_from_hint,
    _dedupe_candidate_names,
    _fuse_candidate_names_rrf,
    _merge_resolution_hint,
    _recall_fallback_candidates,
    _resolution_key,
    _TermResolutionHint,
)

logger = logging.getLogger(__name__)


def normalize_cc_result_with_hints(
    cc_result: CCConfirmResult | None,
    cc_registry: dict[int, CCTermMeta],
    hints: dict[tuple[str, str], _TermResolutionHint],
    recall_map: dict[str, list[dict[str, Any]]],
) -> CCConfirmResult | None:
    """根据历史确认提示归一化单条 complex_condition 的确认结果。

    若前序确认值出现在当前 cc 候选中，直接复用该确认值；若不在候选中，
    则用 RRF 融合当前候选与历史候选，保持两个排序来源的相对贡献。
    """
    if cc_result is None:
        return None

    normalized: list[CCTermConfirmation] = []
    for confirmation in cc_result.confirmations:
        meta = cc_registry.get(confirmation.term_id)
        if meta is None:
            normalized.append(confirmation)
            continue

        hint = hints.get(_resolution_key(meta.ktype, meta.raw_text))
        if hint is None:
            normalized.append(confirmation)
            continue

        fallback_candidates = _recall_fallback_candidates(recall_map, meta.ktype, meta.raw_text)
        current_candidates = _dedupe_candidate_names(
            ([confirmation.confirmed] if confirmation.confirmed else [])
            + (confirmation.candidates or fallback_candidates)
        )
        hint_candidates = _candidate_names_from_hint(hint)

        if hint.confirmed and (hint.force_confirm or hint.confirmed in current_candidates):
            normalized.append(
                CCTermConfirmation(
                    term_id=confirmation.term_id,
                    confirmed=hint.confirmed,
                    candidates=[],
                    reason=confirmation.reason,
                )
            )
            continue

        fused_candidates = _fuse_candidate_names_rrf([current_candidates, hint_candidates])
        keep_confirmed = bool(
            confirmation.confirmed
            and (hint.confirmed is None or confirmation.confirmed in fused_candidates)
        )
        normalized.append(
            CCTermConfirmation(
                term_id=confirmation.term_id,
                confirmed=confirmation.confirmed if keep_confirmed else None,
                candidates=fused_candidates,
                reason=confirmation.reason,
            )
        )

    return CCConfirmResult(
        confirmations=normalized,
        needs_clarification=any(c.confirmed is None and c.candidates for c in normalized),
    )


def merge_cc_resolution_hints(
    hints: dict[tuple[str, str], _TermResolutionHint],
    cc_result: CCConfirmResult | None,
    cc_registry: dict[int, CCTermMeta],
) -> None:
    """将当前 cc 确认结果写入提示表，供后续 cc_terms 按顺序复用。"""
    if cc_result is None:
        return

    for confirmation in cc_result.confirmations:
        meta = cc_registry.get(confirmation.term_id)
        if meta is None:
            continue
        key = _resolution_key(meta.ktype, meta.raw_text)
        incoming = _TermResolutionHint(
            confirmed=confirmation.confirmed,
            candidates=tuple(confirmation.candidates),
        )
        hints[key] = _merge_resolution_hint(hints.get(key), incoming)


def _dedupe_condition_term_mappings(
    mappings: list[ConditionTermMapping],
) -> list[ConditionTermMapping]:
    """按句子 span 合并重复的 complex_condition 术语映射。

    complex_condition 的替换逻辑基于 ``start/end`` 操作原句。同一个文本 span
    如果同时被解析为 select 和 whereKey，不能在前端展示时替换两次；因此这里按
    ``(start, end, original_term)`` 合并，候选用 RRF 融合以保留不同来源的排序贡献。
    """
    grouped: dict[tuple[int, int, str], list[ConditionTermMapping]] = {}
    order: list[tuple[int, int, str]] = []
    for mapping in mappings:
        key = (mapping.start, mapping.end, mapping.original_term)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(mapping)

    deduped: list[ConditionTermMapping] = []
    for key in order:
        group = grouped[key]
        first = group[0]
        confirmed = next((item.confirmed for item in group if item.confirmed is not None), None)
        candidate_lists = [item.candidates for item in group if item.candidates]
        candidates = [] if confirmed is not None else _fuse_candidate_names_rrf(candidate_lists)
        deduped.append(
            ConditionTermMapping(
                original_term=first.original_term,
                start=first.start,
                end=first.end,
                confirmed=confirmed,
                candidates=candidates,
            )
        )

    return deduped
