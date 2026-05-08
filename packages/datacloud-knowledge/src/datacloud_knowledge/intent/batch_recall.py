"""批量并发术语召回实现。"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import bindparam, text

from datacloud_knowledge.knowledge_search.db.connection import get_session
from datacloud_knowledge.query.search.bm25 import (
    _has_jieba_column,
    _has_name_keywords_column,
    _jieba_tokenize,
)
from datacloud_knowledge.query.search.rrf import rrf_fuse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .typed_recall import CandidateDict


class TypedKeywordState(Protocol):
    keyword: str
    ktype: str
    search_enabled: bool


log = logging.getLogger(__name__)

_BM25_MIN_SCORE = 0.001
# 向量召回不设最低相似度阈值，统一用 top_k 截断后交给 RRF 融合排序。
# 低质量候选会在 RRF 融合时因排名靠后被自然淘汰。
_VECTOR_MIN_SIMILARITY = 0.0


@dataclass(frozen=True, slots=True)
class RecallRequest:
    map_key: str
    keyword: str
    ktype: str
    type_filter: frozenset[str] | None
    is_per_type: bool
    per_type_limit: int
    scope_code: str | None = None
    is_value_recall: bool = False


@dataclass(frozen=True, slots=True)
class ScopeRecallLayer:
    """A weighted search-scope layer used by layered recall validation."""

    scope_code: str | None
    weight: float = 1.0
    label: str = ""


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    requests: tuple[RecallRequest, ...]
    normal_requests: tuple[RecallRequest, ...]
    per_type_requests: tuple[RecallRequest, ...]


# select/groupBy/orderBy/whereKey 不应召回表/视图/动作等非字段类型的术语。
# 这些 ktype 需要的是可查询的字段（prop），而非数据实体定义（object/view/action）。
# 例如："管理网格综合分析表"是 view 类型术语，不应出现在 select 字段候选中。
_FIELD_ONLY_KTYPES: frozenset[str] = frozenset({"select", "groupBy", "orderBy", "whereKey"})
_NON_FIELD_TYPE_CODES: frozenset[str] = frozenset({"view", "object", "action"})

# 单字兜底只允许中文 CJK 字符进入 tsquery。
# 业务上这是最后一道召回兜底，用来处理人名、地名、简称等短文本被 jieba/子串召回漏掉的情况；
# 安全上必须禁止把用户原始输入里的 SQL/tsquery 操作符、英文标识符、标点直接拼进 to_tsquery。
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

# “其他关键字检索都为空”只指文本关键字召回路径：单字 BM25、jieba 词级 BM25、子串召回。
# vector 是语义召回，不属于关键字检索；即使 vector 有弱相关结果，只要关键字路径全空，仍允许单字兜底补充候选。
_KEYWORD_RECALL_PATHS: frozenset[str] = frozenset({"bm25_and", "jieba", "substring"})


def _post_filter_non_field_types(
    result: dict[str, list[CandidateDict]],
) -> dict[str, list[CandidateDict]]:
    """过滤掉 select/groupBy/orderBy/whereKey 候选中的非字段类型术语。"""
    filtered: dict[str, list[CandidateDict]] = {}
    for map_key, candidates in result.items():
        # map_key 格式: "ktype:keyword"
        ktype = map_key.split(":", 1)[0] if ":" in map_key else ""
        if ktype in _FIELD_ONLY_KTYPES:
            filtered[map_key] = [
                c for c in candidates if c.get("term_type_code") not in _NON_FIELD_TYPE_CODES
            ]
        else:
            filtered[map_key] = candidates
    return filtered


def _dedupe_candidates_by_term_name(candidates: list[CandidateDict]) -> list[CandidateDict]:
    """按展示名去重，同时保留已有排序。

    召回链路里同一个业务名称可能因为别名、不同 term_id、不同召回路径重复出现。
    澄清上下文最终是给用户/LLM 阅读的候选列表，重复展示名只会放大噪声，
    因此这里在候选已经完成 RRF 排序后保留排名最高的一条。
    """
    deduped: list[CandidateDict] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        term_name = str(candidate.get("term_name", ""))
        if term_name in seen_names:
            continue
        seen_names.add(term_name)
        deduped.append(candidate)
    return deduped


def typed_multi_recall_batch(
    items: Sequence[TypedKeywordState],
    *,
    session: Session,
    top_k: int,
    rrf_k: int,
    enable_vector: bool,
    wv_per_type: int,
    scope_code: str | None = None,
    scope_layers: Sequence[ScopeRecallLayer] | None = None,
) -> dict[str, list[CandidateDict]]:
    """批量并发执行 typed multi recall。

    业务含义：对澄清/意图解析阶段抽取出的结构化术语，按 ktype 限定候选类型后进行多路召回，
    输出 ``ktype:keyword -> candidates``，供后续 LLM 确认、澄清卡片或自动消歧使用。

    主流程：
    1. 如果有 scope layers，走分层召回：每个 scope 单独召回，再按 layer 权重融合；
    2. 否则先整理批量请求，跳过空 keyword 和禁用搜索的项；
    3. 并发执行常规召回路径：单字 BM25 AND、jieba 词级 BM25、子串召回、可选向量召回；
    4. 对“文本关键字召回全空”的 keyword 追加中文单字 OR 兜底；
    5. 统一走 RRF 融合、类型过滤、展示名去重和字段类型后过滤。

    单字兜底的动机：短中文值（尤其人名、简称）经常因为词级分词或子串条件过窄而漏召回。
    它只能作为最后补救，不能抢占正常关键字召回结果，否则会显著增加噪声。
    """
    started_at = time.monotonic()
    result: dict[str, list[CandidateDict]] = {}
    normalized_layers = _normalize_scope_layers(scope_layers)
    if normalized_layers:
        result.update(
            _typed_multi_recall_layered(
                items,
                session=session,
                top_k=top_k,
                rrf_k=rrf_k,
                enable_vector=enable_vector,
                wv_per_type=wv_per_type,
                scope_layers=normalized_layers,
            )
        )
        log.info("[recall_perf] batch_total_layered: %.3fs", time.monotonic() - started_at)
        return _post_filter_non_field_types(result)

    batch = _prepare_batch(items, session, wv_per_type=wv_per_type, scope_code=scope_code)

    for item in items:
        if not item.keyword.strip() or not item.search_enabled:
            result.setdefault(f"{item.ktype}:{item.keyword}", [])

    if batch.requests:
        log.debug(
            "[recall_batch] 开始召回: %d 个关键词=[%s]",
            len(batch.requests),
            ", ".join(f"{r.ktype}:{r.keyword!r}" for r in batch.requests),
        )
        path_results = _run_paths_concurrent(batch, top_k=top_k, enable_vector=enable_vector)
        _add_single_char_fallback_results(path_results, batch, top_k=top_k)
        fused = _fuse_and_shape(batch, path_results, top_k=top_k, rrf_k=rrf_k)
        result.update(fused)
        # 逐 keyword 记录召回结果
        for req in batch.requests:
            candidates = fused.get(req.map_key, [])
            if candidates:
                top_names = [c["term_name"] for c in candidates[:3]]
                log.debug(
                    "[recall_batch] %s -> %d 候选 top3=%s",
                    req.map_key,
                    len(candidates),
                    top_names,
                )
            else:
                log.debug("[recall_batch] %s -> 0 候选", req.map_key)

    for item in items:
        map_key = f"{item.ktype}:{item.keyword}"
        result.setdefault(map_key, [])

    log.info("[recall_perf] batch_total: %.3fs", time.monotonic() - started_at)
    return _post_filter_non_field_types(result)


def _typed_multi_recall_layered(
    items: Sequence[TypedKeywordState],
    *,
    session: Session,
    top_k: int,
    rrf_k: int,
    enable_vector: bool,
    wv_per_type: int,
    scope_layers: tuple[ScopeRecallLayer, ...],
) -> dict[str, list[CandidateDict]]:
    """按 scope layer 执行召回，并用加权 RRF 融合每层结果。

    分层召回用于“同一个字段名/值在不同业务场景含义不同”的情况，例如同名指标在 view scope
    和 object scope 下候选不同。这里不能在每个 layer 内提前做单字兜底，否则某个空 layer 的噪声
    会和另一个 layer 的正常命中一起参与融合，违反“正常关键字召回为空才兜底”的业务约束。

    因此流程分两段：
    1. 所有 layer 先只跑常规召回，并记录每层 bm25/jieba/substring/vector 的原始命中；
    2. 如果某个 keyword 在所有 layer 的文本关键字路径都为空，则追加单字兜底；
       vector 命中不阻止兜底，因为 vector 是语义召回，不属于“关键字检索”。
    """
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


def _candidate_top_names(candidates: Sequence[CandidateDict], *, limit: int = 3) -> list[str]:
    """Return a compact candidate-name preview for recall debug logs."""
    return [str(candidate.get("term_name", "")) for candidate in candidates[:limit]]


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
    但 vector 是语义召回，不属于“关键字检索”；用户要求的单字兜底语义是
    “bm25/jieba/substring 等文本关键字路径都没有命中时，加回单字检索”。

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


def _filter_batch_by_map_keys(
    batch: PreparedBatch,
    map_keys: set[str],
) -> PreparedBatch:
    requests = tuple(request for request in batch.requests if request.map_key in map_keys)
    return PreparedBatch(
        requests=requests,
        normal_requests=tuple(request for request in requests if not request.is_per_type),
        per_type_requests=tuple(request for request in requests if request.is_per_type),
    )


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


def _prepare_batch(
    items: Sequence[TypedKeywordState],
    session: Session,
    *,
    wv_per_type: int,
    scope_code: str | None = None,
) -> PreparedBatch:
    from . import typed_recall as serial_recall

    requests: list[RecallRequest] = []
    seen: set[str] = set()
    category_cache: dict[frozenset[int], set[str]] = {}

    for item in items:
        keyword = item.keyword.strip()
        if not keyword or not item.search_enabled:
            continue

        map_key = f"{item.ktype}:{keyword}"
        if map_key in seen:
            continue
        seen.add(map_key)

        allowed_categories = serial_recall.KTYPE_CATEGORY_MAP.get(item.ktype)
        if allowed_categories is None:
            type_filter: set[str] | None = None
        else:
            cat_key = frozenset(allowed_categories)
            if cat_key not in category_cache:
                category_cache[cat_key] = serial_recall._load_type_codes_by_category(
                    session, allowed_categories
                )
            type_filter = category_cache[cat_key]
            if not type_filter:
                continue

        frozen_filter = frozenset(type_filter) if type_filter is not None else None
        is_per_type = (
            item.ktype == "whereValue" and frozen_filter is not None and len(frozen_filter) > 1
        )
        requests.append(
            RecallRequest(
                map_key=map_key,
                keyword=keyword,
                ktype=item.ktype,
                type_filter=frozen_filter,
                is_per_type=is_per_type,
                per_type_limit=wv_per_type if is_per_type else 0,
                scope_code=scope_code,
                is_value_recall=item.ktype == "whereValue",
            )
        )

    return PreparedBatch(
        requests=tuple(requests),
        normal_requests=tuple(request for request in requests if not request.is_per_type),
        per_type_requests=tuple(request for request in requests if request.is_per_type),
    )


def _run_paths_concurrent(
    batch: PreparedBatch,
    *,
    top_k: int,
    enable_vector: bool,
) -> dict[str, dict[str, list[tuple[str, str, str, str, str]]]]:
    futures: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures["bm25_and"] = pool.submit(_batch_bm25_and, batch, top_k=top_k)
        futures["jieba"] = pool.submit(_batch_jieba_bm25, batch, top_k=top_k)
        futures["substring"] = pool.submit(_batch_substring, batch, top_k=top_k)
        if enable_vector:
            futures["vector"] = pool.submit(_batch_vector, batch, top_k=top_k)

        results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=30)
            except Exception:
                log.warning("Path %s failed", name, exc_info=True)
                results[name] = {}
    return results


def _add_single_char_fallback_results(
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
    batch: PreparedBatch,
    *,
    top_k: int,
) -> None:
    """为常规文本关键字召回全空的请求追加中文单字 OR 兜底结果。

    业务含义：用户输入的短中文值可能无法通过完整词匹配，但其中的单字仍可能出现在候选名称中。
    例如“黄升”没有完整命中时，可以退化为 ``黄 | 升``，召回“黄药师”“黄蓉”等弱候选，
    让澄清阶段至少有可展示/可确认的备选项。

    流程约束：
    1. 先检查 bm25_and / jieba / substring 三类关键字召回是否都为空；
    2. 只对包含 CJK 字符的 keyword 生成兜底请求；
    3. 复用批量 tsquery 查询，保留 scope、type_filter、per-type 限制；
    4. 将结果作为额外 path 写回 ``path_results``，继续走原有 RRF 和候选整形逻辑。
    """
    fallback_batch = _build_single_char_fallback_batch(batch, path_results)
    if not fallback_batch.requests:
        return

    fallback_results = _batch_single_char_fallback(fallback_batch, top_k=top_k)
    if fallback_results:
        path_results["single_char_fallback"] = fallback_results


def _build_single_char_fallback_batch(
    batch: PreparedBatch,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
) -> PreparedBatch:
    """从原始 batch 中筛出需要单字兜底的请求。

    这里不直接查询数据库，只做“是否应该兜底”的业务判定：
    文本关键字召回路径全空，并且 keyword 能生成安全的 CJK 单字 tsquery。
    """
    requests = tuple(
        request
        for request in batch.requests
        if _all_existing_paths_empty(request, path_results)
        and _single_char_fallback_tsquery(request.keyword)
    )
    return PreparedBatch(
        requests=requests,
        normal_requests=tuple(request for request in requests if not request.is_per_type),
        per_type_requests=tuple(request for request in requests if request.is_per_type),
    )


def _all_existing_paths_empty(
    request: RecallRequest,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
) -> bool:
    """判断一个请求的文本关键字召回是否全空。"""
    return all(
        not path_results.get(path_name, {}).get(request.map_key)
        for path_name in _KEYWORD_RECALL_PATHS
    )


def _batch_single_char_fallback(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """执行中文单字兜底召回。

    实现上复用现有 `_run_tsquery_batches()`，而不是直接调用 `bm25_search_with_or()`：
    前者已经支持批量 VALUES 查询、scope 过滤、type_filter、whereValue per-type 分桶；
    后者是单 keyword 底层搜索函数，直接使用会绕过这些业务约束。
    """
    started_at = time.monotonic()
    with get_session() as session:
        if not _has_name_keywords_column(session):
            log.info(
                "[recall_perf] single_char_fallback: %.3fs keywords=%d hits=0",
                time.monotonic() - started_at,
                len(batch.requests),
            )
            return {}

        results = _run_tsquery_batches(
            session,
            normal_requests=batch.normal_requests,
            per_type_requests=batch.per_type_requests,
            top_k=top_k,
            column_name="name_keywords",
            tokenizer=_single_char_fallback_tsquery,
        )
        results = _dedupe_ranked_rows_by_term_name(results)

    log.info(
        "[recall_perf] single_char_fallback: %.3fs keywords=%d hits=%d",
        time.monotonic() - started_at,
        len(batch.requests),
        sum(len(hits) for hits in results.values()),
    )
    return results


def _single_char_fallback_tsquery(keyword: str) -> str:
    """将 keyword 转换为安全的中文单字 OR tsquery。

    只保留去重后的 CJK 单字，并由程序固定插入 ``|`` 操作符；用户输入里的英文、数字、下划线、
    标点和 tsquery 操作符全部丢弃，避免 `to_tsquery('simple', ...)` 解析异常或语义注入。
    """
    seen: set[str] = set()
    chars: list[str] = []
    for char in keyword.strip():
        if char in seen or not _CJK_CHAR_RE.fullmatch(char):
            continue
        seen.add(char)
        chars.append(char)
    return " | ".join(chars)


def _dedupe_ranked_rows_by_term_name(
    results: dict[str, list[tuple[str, str, str, str, str]]],
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """对兜底原始行按展示名去重。

    单字 OR 召回天然更宽，容易把同一展示名的多个别名/类型行都召回来。
    在进入 RRF 前先按 term_name 保留第一条，可以减少澄清上下文里的重复候选。
    """
    deduped: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for map_key, rows in results.items():
        seen_names: set[str] = set()
        unique_rows: list[tuple[str, str, str, str, str]] = []
        for row in rows:
            term_name = row[1]
            if term_name in seen_names:
                continue
            seen_names.add(term_name)
            unique_rows.append(row)
        deduped[map_key] = unique_rows
    return deduped


def _fuse_and_shape(
    batch: PreparedBatch,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
    *,
    top_k: int,
    rrf_k: int,
) -> dict[str, list[CandidateDict]]:
    from . import typed_recall as serial_recall

    result: dict[str, list[CandidateDict]] = {}
    for req in batch.requests:
        ranked_lists: list[list[tuple[str, str, str, str, str]]] = []
        for path_hits in path_results.values():
            hits = path_hits.get(req.map_key, [])
            if hits:
                ranked_lists.append(hits)

        if ranked_lists:
            fused = rrf_fuse(ranked_lists, k=rrf_k, top_n=top_k * 3)
            if req.is_per_type:
                diversified = [
                    (
                        candidate.term_id,
                        candidate.term_name,
                        candidate.name_id,
                        candidate.term_type_code,
                        candidate.term_code,
                    )
                    for candidate in fused
                ]
                diversified = serial_recall._diversify_by_type(
                    diversified,
                    per_type=req.per_type_limit,
                )
                candidates = _shape_diversified_candidates(
                    diversified,
                    fused,
                    req.type_filter,
                    top_k=top_k,
                )
            else:
                candidates = serial_recall._shape_candidates(fused, req.type_filter, top_k=top_k)
        else:
            candidates = []
        result[req.map_key] = _dedupe_candidates_by_term_name(candidates)
    return result


def _batch_bm25_and(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    started_at = time.monotonic()
    with get_session() as session:
        if not _has_name_keywords_column(session):
            log.info(
                "[recall_perf] bm25_and: %.3fs keywords=%d hits=0",
                time.monotonic() - started_at,
                len(batch.requests),
            )
            return {}

        results = _run_tsquery_batches(
            session,
            normal_requests=batch.normal_requests,
            per_type_requests=batch.per_type_requests,
            top_k=top_k,
            column_name="name_keywords",
            tokenizer=lambda keyword: " & ".join(list(keyword)),
        )

    log.info(
        "[recall_perf] bm25_and: %.3fs keywords=%d hits=%d",
        time.monotonic() - started_at,
        len(batch.requests),
        sum(len(hits) for hits in results.values()),
    )
    return results


def _batch_jieba_bm25(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    started_at = time.monotonic()
    with get_session() as session:
        if not _has_jieba_column(session):
            log.info(
                "[recall_perf] jieba: %.3fs keywords=%d hits=0",
                time.monotonic() - started_at,
                len(batch.requests),
            )
            return {}

        results = _run_tsquery_batches(
            session,
            normal_requests=batch.normal_requests,
            per_type_requests=batch.per_type_requests,
            top_k=top_k,
            column_name="name_keywords_jieba",
            tokenizer=_jieba_tokenize,
        )

    log.info(
        "[recall_perf] jieba: %.3fs keywords=%d hits=%d",
        time.monotonic() - started_at,
        len(batch.requests),
        sum(len(hits) for hits in results.values()),
    )
    return results


def _batch_substring(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    started_at = time.monotonic()
    with get_session() as session:
        results: dict[str, list[tuple[str, str, str, str, str]]] = {}
        for type_filter, requests in _group_requests_by_filter(batch.normal_requests).items():
            if requests:
                results.update(_run_substring_query(session, requests, type_filter, top_k=top_k))
        for type_filter, requests in _group_requests_by_filter(batch.per_type_requests).items():
            if requests:
                results.update(
                    _run_substring_query(
                        session,
                        requests,
                        type_filter,
                        top_k=top_k,
                        per_type_limit=requests[0].per_type_limit,
                    )
                )

    log.info(
        "[recall_perf] substring: %.3fs keywords=%d hits=%d",
        time.monotonic() - started_at,
        len(batch.requests),
        sum(len(hits) for hits in results.values()),
    )
    return results


def _batch_vector(
    batch: PreparedBatch,
    *,
    top_k: int,
    min_similarity: float = _VECTOR_MIN_SIMILARITY,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    started_at = time.monotonic()
    if not batch.requests:
        return {}

    from datacloud_knowledge.query.embedding import get_embedding_service

    svc = get_embedding_service()
    vectors = svc.get_text_embedding_batch([req.keyword for req in batch.requests])
    vector_strs = ["[" + ",".join(map(str, vec)) + "]" for vec in vectors]

    # N 个独立查询并发执行，每个走 HNSW 索引
    results: dict[str, list[tuple[str, str, str, str, str]]] = {}
    with ThreadPoolExecutor(max_workers=min(len(batch.requests), 8)) as pool:
        futures = {
            pool.submit(
                _run_single_vector_query,
                req,
                vector_strs[idx],
                top_k=top_k,
                min_similarity=min_similarity,
            ): req
            for idx, req in enumerate(batch.requests)
        }
        for future, req in futures.items():
            try:
                results.update(future.result(timeout=30))
            except Exception:
                log.warning("Vector query failed for %s", req.map_key, exc_info=True)

    log.info(
        "[recall_perf] vector: %.3fs keywords=%d hits=%d",
        time.monotonic() - started_at,
        len(batch.requests),
        sum(len(hits) for hits in results.values()),
    )
    return results


def _run_tsquery_batches(
    session: Session,
    *,
    normal_requests: tuple[RecallRequest, ...],
    per_type_requests: tuple[RecallRequest, ...],
    top_k: int,
    column_name: str,
    tokenizer: Callable[[str], str],
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    results: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for type_filter, requests in _group_requests_by_filter(normal_requests).items():
        if requests:
            results.update(
                _run_tsquery_query(
                    session,
                    requests,
                    type_filter,
                    top_k=top_k,
                    column_name=column_name,
                    tokenizer=tokenizer,
                )
            )
    for type_filter, requests in _group_requests_by_filter(per_type_requests).items():
        if requests:
            results.update(
                _run_tsquery_query(
                    session,
                    requests,
                    type_filter,
                    top_k=top_k,
                    column_name=column_name,
                    tokenizer=tokenizer,
                    per_type_limit=requests[0].per_type_limit,
                )
            )
    return results


def _group_requests_by_filter(
    requests: tuple[RecallRequest, ...],
) -> dict[frozenset[str] | None, list[RecallRequest]]:
    grouped: dict[frozenset[str] | None, list[RecallRequest]] = defaultdict(list)
    for request in requests:
        grouped[request.type_filter].append(request)
    return grouped


def _run_tsquery_query(
    session: Session,
    requests: list[RecallRequest],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
    column_name: str,
    tokenizer: Callable[[str], str],
    per_type_limit: int = 0,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    scope_code = requests[0].scope_code if requests else None
    # ontology-term recall (select/groupBy/orderBy/whereKey) uses strict scope;
    # value-term recall (whereValue) allows legacy unscoped rows
    is_strict = bool(requests) and not requests[0].is_value_recall
    scope_clause = _build_effective_scope_clause(scope_code, strict=is_strict)
    input_values, params = _build_values_clause(
        requests,
        value_getter=lambda request: str(tokenizer(request.keyword)),
    )
    if per_type_limit > 0:
        sql = _build_tsquery_sql(
            input_values=input_values,
            tsvector_column=column_name,
            order_expr="score DESC",
            type_filter=type_filter,
            per_type_limit=per_type_limit,
            scope_clause=scope_clause,
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_tsquery_sql(
            input_values=input_values,
            tsvector_column=column_name,
            order_expr="score DESC",
            type_filter=type_filter,
            scope_clause=scope_clause,
        )
        params["per_kw_limit"] = top_k * 3

    params["min_score"] = _BM25_MIN_SCORE
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    if scope_clause:
        params.update(_build_scope_params(scope_code))
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())


def _run_substring_query(
    session: Session,
    requests: list[RecallRequest],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
    per_type_limit: int = 0,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    scope_code = requests[0].scope_code if requests else None
    is_strict = bool(requests) and not requests[0].is_value_recall
    scope_clause = _build_effective_scope_clause(scope_code, strict=is_strict)
    input_values, params = _build_values_clause(
        requests,
        value_getter=lambda request: request.keyword,
    )
    if per_type_limit > 0:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
            per_type_limit=per_type_limit,
            scope_clause=scope_clause,
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
            scope_clause=scope_clause,
        )
        params["per_kw_limit"] = top_k * 3
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    if scope_clause:
        params.update(_build_scope_params(scope_code))
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())


# ---------------------------------------------------------------------------
# Single-vector query (HNSW-friendly: ORDER BY embedding <=> :constant LIMIT k)
# ---------------------------------------------------------------------------


def _run_single_vector_query(
    req: RecallRequest,
    vector_str: str,
    *,
    top_k: int,
    min_similarity: float,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """\u5355 keyword \u5411\u91cf\u67e5\u8be2\uff0c\u4f7f\u7528 HNSW \u7d22\u5f15 (ORDER BY <=> :constant LIMIT k)\u3002"""
    with get_session() as session:
        params: dict[str, Any] = {
            "vector": vector_str,
            "min_similarity": min_similarity,
        }
        scope_clause = _build_effective_scope_clause(req.scope_code, strict=not req.is_value_recall)
        if req.is_per_type and req.type_filter is not None:
            sql: Any = _build_vector_sql(
                typed=True,
                per_type=True,
                scope_clause=scope_clause,
            )
            params["type_codes"] = sorted(req.type_filter)
            params["per_type_limit"] = req.per_type_limit
            params["limit"] = top_k * 3 * len(req.type_filter)
        elif req.type_filter is not None:
            sql = _build_vector_sql(
                typed=True,
                per_type=False,
                scope_clause=scope_clause,
            )
            params["type_codes"] = sorted(req.type_filter)
            params["limit"] = top_k * 3
        else:
            sql = _build_vector_sql(
                typed=False,
                per_type=False,
                scope_clause=scope_clause,
            )
            params["limit"] = top_k * 3
        if scope_clause:
            params.update(_build_scope_params(req.scope_code))

        rows = session.execute(sql, params).fetchall()
        results: list[tuple[str, str, str, str, str]] = []
        for term_id, term_name, name_id, term_type_code, score, term_code in rows:
            if float(score) >= min_similarity:
                results.append(
                    (
                        str(term_id),
                        str(term_name),
                        str(name_id),
                        str(term_type_code),
                        str(term_code),
                    )
                )
        return {req.map_key: results} if results else {}


def _build_values_clause(
    requests: list[RecallRequest],
    *,
    value_getter: Callable[[RecallRequest], str],
    cast_type: str | None = None,
) -> tuple[str, dict[str, Any]]:
    values_sql: list[str] = []
    params: dict[str, Any] = {}
    for index, request in enumerate(requests):
        keyword_key_name = f"keyword_key_{index}"
        value_name = f"value_{index}"
        value_expr = f":{value_name}"
        if cast_type is not None:
            value_expr = f"CAST(:{value_name} AS {cast_type})"
        values_sql.append(f"(:{keyword_key_name}, {value_expr})")
        params[keyword_key_name] = request.map_key
        params[value_name] = value_getter(request)
    return ", ".join(values_sql), params


def _build_tsquery_sql(
    *,
    input_values: str,
    tsvector_column: str,
    order_expr: str,
    type_filter: frozenset[str] | None,
    per_type_limit: int = 0,
    scope_clause: str = "",
) -> object:
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n            AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key, t.term_type_code
                       ORDER BY ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
              JOIN term t ON tn.term_id = t.term_id
              WHERE tn.{tsvector_column} IS NOT NULL{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_type_limit AND score >= :min_score
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key
                       ORDER BY ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
              JOIN term t ON tn.term_id = t.term_id
              WHERE tn.{tsvector_column} IS NOT NULL{type_clause}{scope_clause}
                AND ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) >= :min_score
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_kw_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)

    if type_filter is not None:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _build_substring_sql(
    *,
    input_values: str,
    type_filter: frozenset[str] | None,
    per_type_limit: int = 0,
    scope_clause: str = "",
) -> object:
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n                  AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     LENGTH(tn.name_text)::float AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key, t.term_type_code
                       ORDER BY LENGTH(tn.name_text) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON (
                    POSITION(tn.name_text IN i.keyword_text) > 0
                    OR POSITION(i.keyword_text IN tn.name_text) > 0
                  )
              JOIN term t ON tn.term_id = t.term_id
              WHERE 1 = 1{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_type_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     LENGTH(tn.name_text)::float AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key
                       ORDER BY LENGTH(tn.name_text) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON (
                    POSITION(tn.name_text IN i.keyword_text) > 0
                    OR POSITION(i.keyword_text IN tn.name_text) > 0
                  )
              JOIN term t ON tn.term_id = t.term_id
              WHERE 1 = 1{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_kw_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)

    if type_filter is not None:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _build_effective_scope_clause(scope_code: str | None, *, strict: bool = False) -> str:
    """Build scope SQL clause for recall filtering.

    Args:
        scope_code: View/object code to filter by. Empty = no filter.
        strict: If True, exclude legacy ``search_scope = '{}'`` rows.
                Use strict=True for ontology-term recall (prop aliases only).
                Use strict=False for value-term recall (enterprise names etc.).
    """
    if not scope_code:
        return ""
    base = """
                  AND (
                        tn.search_scope @> CAST(:view_scope AS jsonb)
                        OR tn.search_scope @> CAST(:obj_scope AS jsonb)
                        OR tn.search_scope @> CAST('{"scope":"global"}' AS jsonb)"""
    if strict:
        return base + "\n                  )"
    return base + "\n                        OR tn.search_scope = '{}'::jsonb\n                  )"


def _build_scope_params(scope_code: str | None) -> dict[str, str]:
    if not scope_code:
        return {}
    return {
        "view_scope": json.dumps({"scope": "view", "code": scope_code}),
        "obj_scope": json.dumps({"scope": "object", "code": scope_code}),
    }


def _build_vector_sql(*, typed: bool, per_type: bool, scope_clause: str = "") -> object:
    type_clause = ""
    if typed:
        type_clause = "\n              AND t.term_type_code IN :type_codes"

    if per_type:
        sql = f"""
            SELECT term_id, term_name, name_id, term_type_code, score, term_code
            FROM (
                SELECT top_n.term_id,
                       top_n.term_name,
                       top_n.name_id,
                       top_n.term_type_code,
                       top_n.score,
                       top_n.term_code,
                       ROW_NUMBER() OVER (
                          PARTITION BY top_n.term_type_code
                          ORDER BY top_n.score DESC
                       ) AS rn
                FROM (
                    SELECT tn.term_id,
                           tn.name_text AS term_name,
                           tn.name_id,
                           t.term_type_code,
                           1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score,
                           t.term_code
                    FROM term_name tn
                    JOIN term t ON tn.term_id = t.term_id
                    WHERE tn.name_embedding IS NOT NULL{type_clause}{scope_clause}
                    ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
                    LIMIT :limit
                ) top_n
            ) ranked
            WHERE rn <= :per_type_limit AND score >= :min_similarity
            ORDER BY score DESC
        """
    else:
        sql = f"""
            SELECT tn.term_id,
                   tn.name_text AS term_name,
                   tn.name_id,
                   t.term_type_code,
                   1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score,
                   t.term_code
            FROM term_name tn
            JOIN term t ON tn.term_id = t.term_id
            WHERE tn.name_embedding IS NOT NULL{type_clause}{scope_clause}
            ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
            LIMIT :limit
        """

    sql_obj = text(sql)
    if typed:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _collect_ranked_rows(rows: Any) -> dict[str, list[tuple[str, str, str, str, str]]]:
    grouped: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)
    for keyword_key, term_id, term_name, name_id, term_type_code, _score, term_code in rows:
        grouped[str(keyword_key)].append(
            (
                str(term_id),
                str(term_name),
                str(name_id),
                str(term_type_code),
                str(term_code),
            )
        )
    return dict(grouped)


def _shape_diversified_candidates(
    diversified: list[tuple[str, str, str, str, str]],
    fused: list[Any],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
) -> list[CandidateDict]:
    score_map = {candidate.term_id: candidate.rrf_score for candidate in fused}
    candidates: list[CandidateDict] = []
    for term_id, term_name, name_id, term_type_code, term_code in diversified:
        if type_filter is not None and term_type_code not in type_filter:
            continue
        score = float(score_map.get(term_id, 0.0))
        candidates.append(
            {
                "term_id": term_id,
                "term_name": term_name,
                "term_type_code": term_type_code,
                "match_type": "multi_recall",
                "confidence": min(score * 10, 1.0),
                "score": score,
                "name_id": name_id,
                "term_code": term_code,
            }
        )
        if len(candidates) >= top_k:
            break
    return candidates
