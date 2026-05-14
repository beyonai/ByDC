"""批量召回路径实现：BM25 AND / jieba BM25 / 子串 / 向量 + 辅助查询函数。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from datacloud_knowledge.adapters.opengauss.engine import PostgresSearchEngine
from datacloud_knowledge.retrieval.tokenizers import create_tokenizer

from ._models import _VECTOR_MIN_SIMILARITY, PreparedBatch, RecallRequest

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
    *,
    normal_requests: tuple[RecallRequest, ...],
    per_type_requests: tuple[RecallRequest, ...],
    top_k: int,
    column_name: str,
    tokenizer: Callable[[str], str],
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """按 type_filter 分组后执行批量 tsquery 查询，由 engine 封装 SQL 执行。"""
    engine = PostgresSearchEngine()
    results: dict[str, list[tuple[str, str, str, str, str]]] = {}
    if normal_requests:
        results.update(
            engine.search_bm25_batch(
                list(normal_requests),
                top_k=top_k,
                column_name=column_name,
                tokenizer_fn=tokenizer,
                per_type_limit=0,
            )
        )
    if per_type_requests:
        results.update(
            engine.search_bm25_batch(
                list(per_type_requests),
                top_k=top_k,
                column_name=column_name,
                tokenizer_fn=tokenizer,
                per_type_limit=per_type_requests[0].per_type_limit,
            )
        )
    return results


def _batch_bm25_and(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """单字 BM25 AND 召回：强制所有单字同时出现才命中。"""
    started_at = time.monotonic()
    engine = PostgresSearchEngine()
    if not engine._check_column_exists("name_keywords"):
        log.info(
            "[recall_perf] bm25_and: %.3fs keywords=%d hits=0",
            time.monotonic() - started_at,
            len(batch.requests),
        )
        return {}

    results = _run_tsquery_batches(
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
    engine = PostgresSearchEngine()
    if not engine._check_column_exists("name_keywords_jieba"):
        log.info(
            "[recall_perf] jieba: %.3fs keywords=%d hits=0",
            time.monotonic() - started_at,
            len(batch.requests),
        )
        return {}

    results = _run_tsquery_batches(
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
    engine = PostgresSearchEngine()
    results: dict[str, list[tuple[str, str, str, str, str]]] = {}
    if batch.normal_requests:
        results.update(
            engine.search_substring_batch(
                list(batch.normal_requests),
                top_k=top_k,
                per_type_limit=0,
            )
        )
    if batch.per_type_requests:
        results.update(
            engine.search_substring_batch(
                list(batch.per_type_requests),
                top_k=top_k,
                per_type_limit=batch.per_type_requests[0].per_type_limit,
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
    engine = PostgresSearchEngine()
    per_type = req.per_type_limit if req.is_per_type else 0
    return engine.search_vector_batch(
        [req],
        top_k=top_k,
        per_type_limit=per_type,
        vector_str=vector_str,
    )


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

    from datacloud_knowledge.retrieval.embedding import get_embedding_service

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
