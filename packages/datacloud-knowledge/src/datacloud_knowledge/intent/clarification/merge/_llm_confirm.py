"""LLM confirmation merge — combine pre-resolve, main LLM, and CC LLM results.

merge_confirmed_common is the shared merge kernel; merge_to_confirmed_query
and merge_to_confirmed_compute wrap it into typed result structs.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from datacloud_knowledge.intent.clarification._patch import apply_value_list, set_by_path
from datacloud_knowledge.intent.clarification.models import (
    CCConfirmResult,
    CCTermMeta,
    ClarificationConfirmedNotInRecallError,
    ClarifyItem,
    ConditionTermMapping,
    ConfirmedCondition,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)

from ._cc_normalize import _dedupe_condition_term_mappings
from ._hints import _recall_fallback_candidates
from ._pre_resolve import apply_pre_resolve_results

logger = logging.getLogger(__name__)


class _MergeConfirmed(Protocol):
    """将公共确认结果合并为指定结构类型。"""

    def __call__(
        self,
        pre: PreResolveResult,
        main_result: MainConfirmResult | None,
        cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
        term_registry: dict[int, TermMeta],
        structured_input: dict[str, Any],
        main_terms: list[ExtractedTerm],
        *,
        recall_map: dict[str, list[dict[str, Any]]] | None = None,
    ) -> ConfirmedStructuredQuery | ConfirmedStructuredCompute: ...


# ── Main merge logic ──────────────────────────────────────────────────


def merge_confirmed_common(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], list[ClarifyItem], list[ConfirmedCondition], bool]:
    """合并分治确认结果的共享逻辑。

    Returns:
        (patched_result, clarify_items, confirmed_conditions, needs_clarification)
    """
    result = json.loads(json.dumps(structured_input, ensure_ascii=False))

    # 1. 回填 pre_resolve 已确认字段
    apply_pre_resolve_results(result, main_terms, pre)

    # 2. 回填 main LLM 确认结果（fail-closed: LLM 失败时强制澄清）
    clarify_items: list[ClarifyItem] = []
    llm_failed = False
    # 收集 whereValue 的 LLM 确认结果，稍后批量回填
    value_confirmations: dict[
        str, list[tuple[int, str]]
    ] = {}  # path → [(index_in_list, confirmed)]
    if main_result:
        covered_ids: set[int] = set()
        # 先统计每个 value path 下有多少个术语（用于确定列表索引）
        value_path_counters: dict[str, int] = {}
        for tc in main_result.confirmations:
            meta = term_registry.get(tc.term_id)
            if meta is None:
                continue
            covered_ids.add(tc.term_id)
            if meta.ktype == "whereValue" and tc.confirmed:
                _validate_confirmed_in_recall(tc.confirmed, recall_map, meta.ktype, meta.raw_text)
                idx = value_path_counters.get(meta.path, 0)
                value_path_counters[meta.path] = idx + 1
                value_confirmations.setdefault(meta.path, []).append((idx, tc.confirmed))
            elif tc.confirmed:
                _validate_confirmed_in_recall(tc.confirmed, recall_map, meta.ktype, meta.raw_text)
                set_by_path(result, meta.path, tc.confirmed)
            elif tc.candidates:
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=tc.candidates,
                        reason=tc.reason,
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )
            else:
                # confirmed=None, candidates=[] → fail-closed
                llm_failed = True
                fallback_candidates = _recall_fallback_candidates(
                    recall_map, meta.ktype, meta.raw_text
                )
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=fallback_candidates,
                        reason=tc.reason or "LLM 无法确认且无候选",
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )
        # 检查 LLM 遗漏的 term_id → 强制澄清
        missing_ids = set(term_registry) - covered_ids
        if missing_ids:
            llm_failed = True
            logger.warning(
                "[merge] LLM 遗漏 %d 个术语: %s",
                len(missing_ids),
                [term_registry[tid].raw_text for tid in missing_ids],
            )
            for tid in missing_ids:
                meta = term_registry[tid]
                fallback_candidates = _recall_fallback_candidates(
                    recall_map, meta.ktype, meta.raw_text
                )
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=fallback_candidates,
                        reason="LLM 确认遗漏，需要人工确认",
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )

        # 批量回填 whereValue 列表（列表感知，不覆盖整个 value）
        for vpath, idx_vals in value_confirmations.items():
            apply_value_list(result, vpath, idx_vals)

    elif term_registry:
        # LLM 失败但有未确认术语 → fail-closed，强制澄清
        llm_failed = True
        logger.warning("[merge] main LLM 确认失败，%d 个术语强制标记为需澄清", len(term_registry))
        for meta in term_registry.values():
            fallback_candidates = _recall_fallback_candidates(recall_map, meta.ktype, meta.raw_text)
            clarify_items.append(
                ClarifyItem(
                    keyword=meta.raw_text,
                    candidates=fallback_candidates,
                    reason="LLM 确认失败，需要人工确认",
                    source=meta.ktype,
                    path=f"/{meta.path.replace('.', '/')}",
                )
            )

    # 3. 组装 confirmed_conditions（fail-closed: cc LLM 失败时也强制澄清）
    confirmed_conditions: list[ConfirmedCondition] = []
    for cc_result, cc_registry in cc_results:
        if cc_result is None:
            if cc_registry:
                llm_failed = True
                logger.warning(
                    "[merge] cc LLM 确认失败，%d 个术语强制标记为需澄清",
                    len(cc_registry),
                )
                for meta in cc_registry.values():
                    clarify_items.append(
                        ClarifyItem(
                            keyword=meta.raw_text,
                            candidates=[],
                            reason="LLM 确认失败，需要人工确认",
                            source="complex_condition",
                            path=f"complex_conditions.{meta.condition_index}",
                        )
                    )
            continue
        if not cc_registry:
            continue
        by_idx: dict[int, list[tuple[int, CCTermMeta]]] = {}
        for tid, meta in cc_registry.items():
            by_idx.setdefault(meta.condition_index, []).append((tid, meta))

        for idx in sorted(by_idx):
            items = by_idx[idx]
            cc_list = structured_input.get("complex_conditions", [])
            original = cc_list[idx] if idx < len(cc_list) else ""

            term_mappings: list[ConditionTermMapping] = []
            mapping_reasons: dict[tuple[int, int, str], str] = {}
            for tid, meta in items:
                tc = next((c for c in cc_result.confirmations if c.term_id == tid), None)
                if tc is None:
                    llm_failed = True
                    logger.warning("[merge] cc LLM 遗漏术语 '%s'", meta.raw_text)
                    term_mappings.append(
                        ConditionTermMapping(
                            original_term=meta.raw_text,
                            start=meta.start,
                            end=meta.end,
                            confirmed=None,
                            candidates=[],
                        )
                    )
                    mapping_reasons[(meta.start, meta.end, meta.raw_text)] = (
                        "LLM 确认遗漏，需要人工确认"
                    )
                    continue
                term_mappings.append(
                    ConditionTermMapping(
                        original_term=meta.raw_text,
                        start=meta.start,
                        end=meta.end,
                        confirmed=tc.confirmed,
                        candidates=tc.candidates,
                    )
                )
                if tc.confirmed is None:
                    mapping_reasons[(meta.start, meta.end, meta.raw_text)] = (
                        tc.reason or "LLM 无法确认且无候选"
                    )
                if tc.confirmed is None and not tc.candidates:
                    llm_failed = True

            term_mappings = _dedupe_condition_term_mappings(term_mappings)
            for tm in term_mappings:
                if tm.confirmed is not None:
                    continue
                reason = mapping_reasons.get(
                    (tm.start, tm.end, tm.original_term),
                    "LLM 无法确认且无候选",
                )
                if tm.candidates:
                    clarify_items.append(
                        ClarifyItem(
                            keyword=tm.original_term,
                            candidates=tm.candidates,
                            reason=reason,
                            source="complex_condition",
                            path=f"complex_conditions.{idx}",
                        )
                    )
                    continue
                llm_failed = True
                clarify_items.append(
                    ClarifyItem(
                        keyword=tm.original_term,
                        candidates=[],
                        reason=reason,
                        source="complex_condition",
                        path=f"complex_conditions.{idx}",
                    )
                )

            confirmed_conditions.append(
                ConfirmedCondition(
                    original_sentence=original,
                    term_mappings=term_mappings,
                )
            )

    needs = (
        llm_failed
        or bool(clarify_items)
        or any(
            tm.confirmed is None and tm.candidates
            for cc in confirmed_conditions
            for tm in cc.term_mappings
        )
    )

    return result, clarify_items, confirmed_conditions, needs


def merge_to_confirmed_query(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> ConfirmedStructuredQuery:
    """合并分治确认结果为 ConfirmedStructuredQuery（兼容下游）。"""
    result, clarify_items, confirmed_conditions, needs = merge_confirmed_common(
        pre,
        main_result,
        cc_results,
        term_registry,
        structured_input,
        main_terms,
        recall_map=recall_map,
    )
    return ConfirmedStructuredQuery(
        select=result.get("select", []),
        filters=result.get("filters", []),
        order_by=result.get("order_by", []),
        limit=result.get("limit"),
        offset=result.get("offset"),
        filter_relation=result.get("filter_relation", "AND"),
        confirmed_conditions=confirmed_conditions,
        clarify_items=clarify_items,
        needs_clarification=needs,
    )


def merge_to_confirmed_compute(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> ConfirmedStructuredCompute:
    """合并分治确认结果为 ConfirmedStructuredCompute（兼容下游）。"""
    result, clarify_items, confirmed_conditions, needs = merge_confirmed_common(
        pre,
        main_result,
        cc_results,
        term_registry,
        structured_input,
        main_terms,
        recall_map=recall_map,
    )
    return ConfirmedStructuredCompute(
        dimensions=result.get("dimensions", []),
        metrics=result.get("metrics", []),
        filters=result.get("filters", []),
        having=result.get("having", []),
        order_by=result.get("order_by", []),
        limit=result.get("limit"),
        filter_relation=result.get("filter_relation", "AND"),
        confirmed_conditions=confirmed_conditions,
        clarify_items=clarify_items,
        needs_clarification=needs,
    )


def _validate_confirmed_in_recall(
    confirmed: str,
    recall_map: dict[str, list[dict[str, Any]]] | None,
    ktype: str,
    raw_text: str,
) -> None:
    """Validate that the LLM-confirmed value exists in the recall candidates.

    Raises ClarificationConfirmedNotInRecallError when:
    - The term was searched (key in recall_map) but had zero results → any confirmed value is hallucination
    - The term had results but the confirmed value is not among them
    If the term was never searched (key not in recall_map, e.g. search_enabled=False),
    skip validation — the LLM may have independently resolved the term.
    """
    if not recall_map:
        return
    key = f"{ktype}:{raw_text}"
    if key not in recall_map:
        return  # term was not searched (e.g. search_enabled=False), skip validation
    candidates = _recall_fallback_candidates(recall_map, ktype, raw_text)
    if not candidates or confirmed not in candidates:
        raise ClarificationConfirmedNotInRecallError(raw_text, confirmed, candidates)
