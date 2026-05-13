"""批量召回 RRF 融合与候选整形层：融合排序、类型过滤、展示名去重、单字兜底。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from datacloud_knowledge.adapters.opengauss.bm25 import _has_name_keywords_column
from datacloud_knowledge.contracts.rrf import rrf_fuse

from ._models import (
    _CJK_CHAR_RE,
    _FIELD_ONLY_KTYPES,
    _KEYWORD_RECALL_PATHS,
    _NON_FIELD_TYPE_CODES,
    PreparedBatch,
    RecallRequest,
)
from ._paths import _run_tsquery_batches

if TYPE_CHECKING:
    from datacloud_knowledge.intent._recall_common import CandidateDict

log = logging.getLogger(__name__)


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


def _shape_diversified_candidates(
    diversified: list[tuple[str, str, str, str, str]],
    fused: list[Any],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
) -> list[CandidateDict]:
    """将按类型分桶后的召回结果整形为 CandidateDict 列表。"""
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


def _fuse_and_shape(
    batch: PreparedBatch,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
    *,
    top_k: int,
    rrf_k: int,
) -> dict[str, list[CandidateDict]]:
    """对每条请求的各路召回结果进行 RRF 融合并整形为 CandidateDict。"""
    from datacloud_knowledge.intent import _recall_common as serial_recall

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


# ── 单字兜底 ──────────────────────────────────────────────────


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


def _all_existing_paths_empty(
    request: RecallRequest,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
) -> bool:
    """判断一个请求的文本关键字召回是否全空。"""
    return all(
        not path_results.get(path_name, {}).get(request.map_key)
        for path_name in _KEYWORD_RECALL_PATHS
    )


def _build_single_char_fallback_batch(
    batch: PreparedBatch,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
) -> PreparedBatch:
    """从原始 batch 中筛出需要单字兜底的请求。

    这里不直接查询数据库，只做"是否应该兜底"的业务判定：
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
    from datacloud_knowledge.adapters.opengauss._db.connection import get_session

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


def _add_single_char_fallback_results(
    path_results: dict[str, dict[str, list[tuple[str, str, str, str, str]]]],
    batch: PreparedBatch,
    *,
    top_k: int,
) -> None:
    """为常规文本关键字召回全空的请求追加中文单字 OR 兜底结果。

    业务含义：用户输入的短中文值可能无法通过完整词匹配，但其中的单字仍可能出现在候选名称中。
    例如"黄升"没有完整命中时，可以退化为 ``黄 | 升``，召回"黄药师""黄蓉"等弱候选，
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
