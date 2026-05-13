"""批量召回路径实现：BM25 AND / jieba BM25 / 子串 / 向量 + 辅助查询函数。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from datacloud_knowledge.adapters.opengauss.engine import PostgresSearchEngine
from datacloud_knowledge.retrieval.tokenizers import create_tokenizer

from ._models import _VECTOR_MIN_SIMILARITY, PreparedBatch, RecallRequest
from ._sql import (
    _build_effective_scope_clause,
    _build_scope_params,
    _build_vector_sql,
    _group_requests_by_filter,
    _run_substring_query,
    _run_tsquery_query,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _jieba_tsquery(text: str) -> str:
    """Jieba 分词后用 `` & `` 拼接为 tsquery 字符串。

    替代原 bm25 模块中的 ``_jieba_tokenize``，使用统一的 Tokenizer 协议。
    """
    tok = create_tokenizer("zh_CN")
    tokens = tok.tokenize(text)
    if not tokens:
        return " & ".join(list(text.strip()))
    return tok.build_tsquery(tokens)


def _run_tsquery_batches(
    session: Session,
    *,
    normal_requests: tuple[RecallRequest, ...],
    per_type_requests: tuple[RecallRequest, ...],
    top_k: int,
    column_name: str,
    tokenizer: Callable[[str], str],
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """按 type_filter 分组后执行批量 tsquery 查询。"""
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


def _batch_bm25_and(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """单字 BM25 AND 召回：强制所有单字同时出现才命中。"""
    from datacloud_knowledge.adapters.opengauss._db.connection import get_session

    started_at = time.monotonic()
    with get_session() as session:
        engine = PostgresSearchEngine(session)
        if not engine._check_column_exists("name_keywords"):
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
    """jieba 词级 BM25 召回：经 jieba 分词后再用 AND 连接进行 BM25 检索。"""

    started_at = time.monotonic()
    from datacloud_knowledge.adapters.opengauss._db.connection import get_session

    with get_session() as session:
        engine = PostgresSearchEngine(session)
        if not engine._check_column_exists("name_keywords_jieba"):
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
            tokenizer=_jieba_tsquery,
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
    """子串匹配召回：keyword 与 term_name 双向包含。"""

    started_at = time.monotonic()
    from datacloud_knowledge.adapters.opengauss._db.connection import get_session

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


def _run_single_vector_query(
    req: RecallRequest,
    vector_str: str,
    *,
    top_k: int,
    min_similarity: float,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """单 keyword 向量查询，使用 HNSW 索引 (ORDER BY <=> :constant LIMIT k)。"""
    from datacloud_knowledge.adapters.opengauss._db.connection import get_session

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


def _batch_vector(
    batch: PreparedBatch,
    *,
    top_k: int,
    min_similarity: float = _VECTOR_MIN_SIMILARITY,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """批量向量召回：并发执行每 keyword 的 HNSW 独立查询。"""
    started_at = time.monotonic()
    if not batch.requests:
        return {}

    from datacloud_knowledge.embedding import get_embedding_service

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
