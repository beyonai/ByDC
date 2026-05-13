"""Resolution hints — cross-stage term resolution reuse hints.

Generates, merges, and applies resolution hints that allow confirmed terms
from earlier stages (pre-resolve, main LLM, CC LLM) to influence later
confirmations via RRF-fused candidate lists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from datacloud_knowledge.intent.clarification._pre_resolve import term_key
from datacloud_knowledge.intent.clarification.models import (
    ExtractedTerm,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)
from datacloud_knowledge.contracts.rrf import rrf_fuse

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TermResolutionHint:
    """已确认术语对后续相同术语的复用提示。"""

    confirmed: str | None
    candidates: tuple[str, ...]
    force_confirm: bool = False


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
