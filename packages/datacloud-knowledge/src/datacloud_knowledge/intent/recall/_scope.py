"""分层 scope 召回管理：按 scope layer 执行加权 RRF 融合。"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ._fusion import _batch_single_char_fallback, _fuse_and_shape, _single_char_fallback_tsquery
from ._models import (
    _KEYWORD_RECALL_PATHS,
    PreparedBatch,
    RecallRequest,
    ScopeRecallLayer,
    TypedKeywordState,
)

if TYPE_CHECKING:
    from datacloud_knowledge.intent._recall_common import CandidateDict

log = logging.getLogger(__name__)


def _normalize_scope_layers(
    scope_layers: Sequence[ScopeRecallLayer] | None,
) -> tuple[ScopeRecallLayer, ...]:
    """Validate, dedupe, and cap scope layers to bound recall cost."""
    if not scope_layers:
        return ()

    normalized: list[ScopeRecallLayer] = []
    seen: set[str | None] = set()
    for layer in scope_layers:
        if layer.weight <= 0:
            continue
        key = layer.scope_code or None
        if key in seen:
            continue
        seen.add(key)
        normalized.append(layer)
        if len(normalized) >= 4:
            break
    return tuple(normalized)


def _candidate_top_names(candidates: Sequence[CandidateDict], *, limit: int = 3) -> list[str]:
    """Return a compact candidate-name preview for recall debug logs."""
    return [str(candidate.get("term_name", "")) for candidate in candidates[:limit]]


def _weighted_fuse_candidate_layers(
    candidate_layers: Sequence[tuple[ScopeRecallLayer, list[CandidateDict]]],
    *,
    top_k: int,
    rrf_k: int,
) -> list[CandidateDict]:
    """Fuse already-ranked layer candidates using weighted reciprocal rank fusion."""
    if not candidate_layers:
        return []

    score_map: dict[str, float] = {}
    info_map: dict[str, CandidateDict] = {}
    for layer, candidates in candidate_layers:
        for rank, candidate in enumerate(candidates, start=1):
            term_id = str(candidate.get("term_id", ""))
            if not term_id:
                continue
            score_map[term_id] = score_map.get(term_id, 0.0) + layer.weight / (rrf_k + rank)
            if term_id not in info_map:
                info_map[term_id] = candidate

    sorted_ids = sorted(score_map, key=lambda term_id: score_map[term_id], reverse=True)[:top_k]
    sorted_ids = _preserve_base_layer_candidate(sorted_ids, candidate_layers, top_k=top_k)
    fused: list[CandidateDict] = []
    for term_id in sorted_ids:
        candidate = dict(info_map[term_id])
        score = score_map[term_id]
        candidate["match_type"] = "layered_multi_recall"
        candidate["score"] = score
        candidate["confidence"] = min(score * 10, 1.0)
        fused.append(candidate)
    return fused


def _preserve_base_layer_candidate(
    sorted_ids: list[str],
    candidate_layers: Sequence[tuple[ScopeRecallLayer, list[CandidateDict]]],
    *,
    top_k: int,
) -> list[str]:
    """Keep the first layer's best candidate visible after weighted layer fusion."""
    if not sorted_ids or not candidate_layers:
        return sorted_ids

    _, base_candidates = candidate_layers[0]
    if not base_candidates:
        return sorted_ids

    base_term_id = str(base_candidates[0].get("term_id", ""))
    if not base_term_id or base_term_id in sorted_ids:
        return sorted_ids

    if len(sorted_ids) < top_k:
        return [*sorted_ids, base_term_id]
    return [*sorted_ids[:-1], base_term_id]


def _filter_batch_by_map_keys(
    batch: PreparedBatch,
    map_keys: set[str],
) -> PreparedBatch:
    """按 map_key 集合过滤 PreparedBatch。"""
    requests = tuple(request for request in batch.requests if request.map_key in map_keys)
    return PreparedBatch(
        requests=requests,
        normal_requests=tuple(request for request in requests if not request.is_per_type),
        per_type_requests=tuple(request for request in requests if request.is_per_type),
    )


def _all_layer_keyword_paths_empty(
    request: RecallRequest,
    per_layer_path_results: Sequence[
        tuple[ScopeRecallLayer, dict[str, dict[str, list[tuple[str, str, str, str, str]]]]]
    ],
) -> bool:
    """判断某请求在所有 scope layer 的文本关键字路径是否全空。"""
    return all(
        not path_results.get(path_name, {}).get(request.map_key)
        for _layer, path_results in per_layer_path_results
        for path_name in _KEYWORD_RECALL_PATHS
    )


def _add_layered_single_char_fallback_results(
    result: dict[str, list[CandidateDict]],
    requests: tuple[RecallRequest, ...],
    per_layer_results: Sequence[tuple[ScopeRecallLayer, dict[str, list[CandidateDict]]]],
    per_layer_batches: Sequence[tuple[ScopeRecallLayer, PreparedBatch]],
    per_layer_path_results: Sequence[
        tuple[ScopeRecallLayer, dict[str, dict[str, list[tuple[str, str, str, str, str]]]]]
    ],
    *,
    top_k: int,
    rrf_k: int,
) -> None:
    """在分层召回中，为文本关键字路径全空的请求补充单字兜底。

    入口动机：分层召回不能只看最终候选是否为空。最终候选可能来自 vector，
    但 vector 是语义召回，不属于"关键字检索"；用户要求的单字兜底语义是
    "bm25/jieba/substring 等文本关键字路径都没有命中时，加回单字检索"。

    因此这里按所有 layer 的原始 path_results 判断：只要任一 layer 的关键字路径命中，
    就不兜底；如果所有 layer 关键字路径都为空，则把单字兜底作为额外 layer 结果
    与已有正常结果一起加权融合，保持和非分层路径一致的 RRF 行为。
    """
    fallback_map_keys = {
        request.map_key
        for request in requests
        if _all_layer_keyword_paths_empty(request, per_layer_path_results)
        and _single_char_fallback_tsquery(request.keyword)
    }
    if not fallback_map_keys:
        return

    fallback_layers: list[tuple[ScopeRecallLayer, dict[str, list[CandidateDict]]]] = []
    for layer, batch in per_layer_batches:
        fallback_batch = _filter_batch_by_map_keys(batch, fallback_map_keys)
        if not fallback_batch.requests:
            continue
        fallback_hits = _batch_single_char_fallback(fallback_batch, top_k=top_k)
        if not fallback_hits:
            continue
        fallback_layers.append(
            (
                layer,
                _fuse_and_shape(
                    fallback_batch,
                    {"single_char_fallback": fallback_hits},
                    top_k=top_k,
                    rrf_k=rrf_k,
                ),
            )
        )

    for request in requests:
        if request.map_key not in fallback_map_keys:
            continue
        candidate_layers = [
            (layer, layer_result.get(request.map_key, []))
            for layer, layer_result in (*per_layer_results, *fallback_layers)
            if layer_result.get(request.map_key)
        ]
        result[request.map_key] = _weighted_fuse_candidate_layers(
            candidate_layers,
            top_k=top_k,
            rrf_k=rrf_k,
        )


def _typed_multi_recall_layered(
    items: Sequence[TypedKeywordState],
    *,
    session,
    top_k: int,
    rrf_k: int,
    enable_vector: bool,
    wv_per_type: int,
    scope_layers: tuple[ScopeRecallLayer, ...],
) -> dict[str, list[CandidateDict]]:
    """按 scope layer 执行召回，并用加权 RRF 融合每层结果。

    分层召回用于"同一个字段名/值在不同业务场景含义不同"的情况，例如同名指标在 view scope
    和 object scope 下候选不同。这里不能在每个 layer 内提前做单字兜底，否则某个空 layer 的噪声
    会和另一个 layer 的正常命中一起参与融合，违反"正常关键字召回为空才兜底"的业务约束。

    因此流程分两段：
    1. 所有 layer 先只跑常规召回，并记录每层 bm25/jieba/substring/vector 的原始命中；
    2. 如果某个 keyword 在所有 layer 的文本关键字路径都为空，则追加单字兜底；
       vector 命中不阻止兜底，因为 vector 是语义召回，不属于"关键字检索"。
    """
    from ._orchestrator import _prepare_batch, _run_paths_concurrent

    per_layer_results: list[tuple[ScopeRecallLayer, dict[str, list[CandidateDict]]]] = []
    per_layer_batches: list[tuple[ScopeRecallLayer, PreparedBatch]] = []
    per_layer_path_results: list[
        tuple[ScopeRecallLayer, dict[str, dict[str, list[tuple[str, str, str, str, str]]]]]
    ] = []
    requests: tuple[RecallRequest, ...] = ()

    for layer in scope_layers:
        layer_started_at = time.monotonic()
        batch = _prepare_batch(
            items,
            session,
            wv_per_type=wv_per_type,
            scope_code=layer.scope_code,
        )
        if not requests:
            requests = batch.requests
        per_layer_batches.append((layer, batch))
        if not batch.requests:
            per_layer_results.append((layer, {}))
            per_layer_path_results.append((layer, {}))
            continue

        path_results = _run_paths_concurrent(batch, top_k=top_k, enable_vector=enable_vector)
        per_layer_path_results.append((layer, path_results))
        shaped = _fuse_and_shape(batch, path_results, top_k=top_k, rrf_k=rrf_k)
        per_layer_results.append((layer, shaped))
        for req in batch.requests:
            candidates = shaped.get(req.map_key, [])
            if candidates:
                log.debug(
                    "[recall_layered] layer=%s scope=%s %s -> %d 候选 top3=%s",
                    layer.label or "scope",
                    layer.scope_code or "unscoped",
                    req.map_key,
                    len(candidates),
                    _candidate_top_names(candidates),
                )
            else:
                log.debug(
                    "[recall_layered] layer=%s scope=%s %s -> 0 候选",
                    layer.label or "scope",
                    layer.scope_code or "unscoped",
                    req.map_key,
                )
        log.info(
            "[recall_perf] layer=%s scope=%s weight=%.3f elapsed=%.3fs hits=%d",
            layer.label or "scope",
            layer.scope_code or "unscoped",
            layer.weight,
            time.monotonic() - layer_started_at,
            sum(len(hits) for hits in shaped.values()),
        )

    result: dict[str, list[CandidateDict]] = {}
    for item in items:
        map_key = f"{item.ktype}:{item.keyword}"
        result.setdefault(map_key, [])

    for req in requests:
        candidate_layers = [
            (layer, layer_result.get(req.map_key, []))
            for layer, layer_result in per_layer_results
            if layer_result.get(req.map_key)
        ]
        result[req.map_key] = _weighted_fuse_candidate_layers(
            candidate_layers,
            top_k=top_k,
            rrf_k=rrf_k,
        )
        if result[req.map_key]:
            log.debug(
                "[recall_layered] fused %s -> %d 候选 top3=%s",
                req.map_key,
                len(result[req.map_key]),
                _candidate_top_names(result[req.map_key]),
            )
        else:
            log.debug("[recall_layered] fused %s -> 0 候选", req.map_key)

    _add_layered_single_char_fallback_results(
        result,
        requests,
        per_layer_results,
        per_layer_batches,
        per_layer_path_results,
        top_k=top_k,
        rrf_k=rrf_k,
    )
    return result
