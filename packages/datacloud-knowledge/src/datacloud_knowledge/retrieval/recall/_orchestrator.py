"""批量召回编排层：请求预处理、并发路径调度、主入口函数。"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from ._fusion import (
    _add_single_char_fallback_results,
    _fuse_and_shape,
    _post_filter_non_field_types,
)
from ._models import PreparedBatch, RecallRequest, ScopeRecallLayer, TypedKeywordState
from ._paths import _batch_bm25_and, _batch_jieba_bm25, _batch_substring, _batch_vector
from ._scope import _normalize_scope_layers, _typed_multi_recall_layered

if TYPE_CHECKING:
    from datacloud_knowledge.retrieval._recall_common import CandidateDict

log = logging.getLogger(__name__)


def _prepare_batch(
    items: Sequence[TypedKeywordState],
    session: Any,
    *,
    wv_per_type: int,
    scope_code: str | None = None,
) -> PreparedBatch:
    """将 TypedKeywordState 序列转换为 PreparedBatch（去重 + 类型过滤 + 分桶）。"""
    from datacloud_knowledge.retrieval import _recall_common as serial_recall

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
                    allowed_categories
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
    """并发执行 4 路召回路径（BM25 AND / jieba / 子串 / 向量）。"""
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


def typed_multi_recall_batch(
    items: Sequence[TypedKeywordState],
    *,
    session: Any,
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
    4. 对"文本关键字召回全空"的 keyword 追加中文单字 OR 兜底；
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
