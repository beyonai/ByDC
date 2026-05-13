"""Result merging — combine pre-resolve, main LLM, and CC LLM results.

Moved from api.py to eliminate local imports and enable independent testing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from datacloud_knowledge.query.search.rrf import rrf_fuse

from ._patch import apply_value_list, set_by_path
from ._pre_resolve import term_key
from .models import (
    CCConfirmResult,
    CCTermConfirmation,
    CCTermMeta,
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TermResolutionHint:
    """已确认术语对后续相同术语的复用提示。"""

    confirmed: str | None
    candidates: tuple[str, ...]
    force_confirm: bool = False


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


# ── Resolution hints ──────────────────────────────────────────────────


def _resolution_key(ktype: str, raw_text: str) -> tuple[str, str]:
    """生成跨主结构与 complex_conditions 复用的术语键。"""
    return ktype, raw_text


def _candidate_names_from_hint(hint: _TermResolutionHint | None) -> list[str]:
    """按确认值优先提取复用提示中的候选名称。"""
    if hint is None:
        return []
    names: list[str] = []
    if hint.confirmed:
        names.append(hint.confirmed)
    names.extend(hint.candidates)
    return _dedupe_candidate_names(names)


def _dedupe_candidate_names(names: list[str]) -> list[str]:
    """按首次出现顺序去重候选名称。"""
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def _fuse_candidate_names_rrf(
    ranked_lists: list[list[str]],
    *,
    limit: int = 5,
) -> list[str]:
    """使用 RRF 融合多个候选排序列表。

    Args:
        ranked_lists: 多个已按相关度排序的候选名称列表。
        limit: 返回候选数量上限。

    Returns:
        RRF 融合后的去重候选名称列表。
    """
    prepared: list[list[tuple[str, str, str, str]]] = []
    for ranked in ranked_lists:
        deduped = _dedupe_candidate_names(ranked)
        if not deduped:
            continue
        prepared.append([(name, name, "", "") for name in deduped])

    if not prepared:
        return []

    return [candidate.term_name for candidate in rrf_fuse(prepared, top_n=limit)]


def _merge_resolution_hint(
    existing: _TermResolutionHint | None,
    incoming: _TermResolutionHint,
) -> _TermResolutionHint:
    """合并同一术语的历史确认提示，候选排序用 RRF 保持稳定。"""
    if existing is None:
        return incoming

    confirmed = existing.confirmed or incoming.confirmed
    candidates = _fuse_candidate_names_rrf(
        [
            _candidate_names_from_hint(existing),
            _candidate_names_from_hint(incoming),
        ]
    )
    return _TermResolutionHint(
        confirmed=confirmed,
        candidates=tuple(candidates),
        force_confirm=existing.force_confirm or incoming.force_confirm,
    )


def merge_pre_resolve_hints(
    hints: dict[tuple[str, str], _TermResolutionHint],
    pre_resolve: PreResolveResult,
    terms: list[ExtractedTerm],
    *,
    force_confirm: bool = False,
) -> None:
    """将 pre_resolve 的确定性结果合并到跨阶段复用提示。"""
    for term in terms:
        resolved = pre_resolve.confirmed.get(term_key(term))
        if resolved is None:
            continue
        key = _resolution_key(term.ktype, term.raw_text)
        incoming = _TermResolutionHint(
            confirmed=resolved.term_name,
            candidates=(resolved.term_name,),
            force_confirm=force_confirm,
        )
        hints[key] = _merge_resolution_hint(hints.get(key), incoming)


def build_main_resolution_hints(
    main_result: MainConfirmResult | None,
    term_registry: dict[int, TermMeta],
) -> dict[tuple[str, str], _TermResolutionHint]:
    """从主结构 LLM 确认结果构建术语复用提示。"""
    hints: dict[tuple[str, str], _TermResolutionHint] = {}

    if main_result is None:
        return hints

    for confirmation in main_result.confirmations:
        meta = term_registry.get(confirmation.term_id)
        if meta is None:
            continue
        key = _resolution_key(meta.ktype, meta.raw_text)
        incoming = _TermResolutionHint(
            confirmed=confirmation.confirmed,
            candidates=tuple(confirmation.candidates),
        )
        hints[key] = _merge_resolution_hint(hints.get(key), incoming)

    return hints


def _recall_fallback_candidates(
    recall_map: dict[str, list[dict[str, Any]]] | None,
    ktype: str,
    raw_text: str,
    limit: int = 5,
) -> list[str]:
    """从召回结果中提取 term_name 列表作为兜底候选。"""
    if not recall_map:
        return []
    key = f"{ktype}:{raw_text}"
    candidates = recall_map.get(key, [])
    return [str(c.get("term_name", "")) for c in candidates[:limit] if c.get("term_name")]


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

    # 1. 回填 pre_resolve 已确认字段（非 whereValue）
    for t in main_terms:
        if t.source != "main" or term_key(t) not in pre.confirmed:
            continue
        if t.ktype == "whereValue":
            continue  # whereValue 列表需要特殊处理
        rf = pre.confirmed[term_key(t)]
        set_by_path(result, t.path, rf.term_name)

    # 1b. 回填 pre_resolve 已确认的 whereValue（列表感知）
    from ._patch import apply_confirmed_values as _apply_confirmed_values

    _apply_confirmed_values(result, main_terms, pre.confirmed, term_source="pre_resolve")

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
                idx = value_path_counters.get(meta.path, 0)
                value_path_counters[meta.path] = idx + 1
                value_confirmations.setdefault(meta.path, []).append((idx, tc.confirmed))
            elif tc.confirmed:
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
