"""批量并发术语召回实现。"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

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
if not log.handlers:
    log.setLevel(logging.INFO)

_SCHEMA = "whale_datacloud"
_BM25_MIN_SCORE = 0.001
_VECTOR_MIN_SIMILARITY = 0.3


@dataclass(frozen=True, slots=True)
class RecallRequest:
    map_key: str
    keyword: str
    ktype: str
    type_filter: frozenset[str] | None
    is_per_type: bool
    per_type_limit: int


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    requests: tuple[RecallRequest, ...]
    normal_requests: tuple[RecallRequest, ...]
    per_type_requests: tuple[RecallRequest, ...]


def typed_multi_recall_batch(
    items: list[TypedKeywordState],
    *,
    session: Session,
    top_k: int,
    rrf_k: int,
    enable_vector: bool,
    wv_per_type: int,
) -> dict[str, list[CandidateDict]]:
    """批量并发执行 typed multi recall。"""
    started_at = time.monotonic()
    result: dict[str, list[CandidateDict]] = {}
    batch = _prepare_batch(items, session, wv_per_type=wv_per_type)

    for item in items:
        if not item.keyword.strip() or not item.search_enabled:
            result.setdefault(f"{item.ktype}:{item.keyword}", [])

    if batch.requests:
        path_results = _run_paths_concurrent(batch, top_k=top_k, enable_vector=enable_vector)
        result.update(_fuse_and_shape(batch, path_results, top_k=top_k, rrf_k=rrf_k))

    for item in items:
        map_key = f"{item.ktype}:{item.keyword}"
        result.setdefault(map_key, [])

    log.info("[recall_perf] batch_total: %.3fs", time.monotonic() - started_at)
    return result


def _prepare_batch(
    items: list[TypedKeywordState],
    session: Session,
    *,
    wv_per_type: int,
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
) -> dict[str, dict[str, list[tuple[str, str, str, str]]]]:
    futures: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures["bm25_and"] = pool.submit(_batch_bm25_and, batch, top_k=top_k)
        futures["jieba"] = pool.submit(_batch_jieba_bm25, batch, top_k=top_k)
        futures["substring"] = pool.submit(_batch_substring, batch, top_k=top_k)
        if enable_vector:
            futures["vector"] = pool.submit(_batch_vector, batch, top_k=top_k)

        results: dict[str, dict[str, list[tuple[str, str, str, str]]]] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=30)
            except Exception:
                log.warning("Path %s failed", name, exc_info=True)
                results[name] = {}
    return results


def _fuse_and_shape(
    batch: PreparedBatch,
    path_results: dict[str, dict[str, list[tuple[str, str, str, str]]]],
    *,
    top_k: int,
    rrf_k: int,
) -> dict[str, list[CandidateDict]]:
    from . import typed_recall as serial_recall

    result: dict[str, list[CandidateDict]] = {}
    for req in batch.requests:
        ranked_lists: list[list[tuple[str, str, str, str]]] = []
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
        result[req.map_key] = candidates
    return result


def _batch_bm25_and(
    batch: PreparedBatch,
    *,
    top_k: int,
) -> dict[str, list[tuple[str, str, str, str]]]:
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
) -> dict[str, list[tuple[str, str, str, str]]]:
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
) -> dict[str, list[tuple[str, str, str, str]]]:
    started_at = time.monotonic()
    with get_session() as session:
        results: dict[str, list[tuple[str, str, str, str]]] = {}
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
) -> dict[str, list[tuple[str, str, str, str]]]:
    started_at = time.monotonic()
    if not batch.requests:
        return {}

    from datacloud_knowledge.query.embedding import get_embedding_service

    svc = get_embedding_service()
    vectors = svc.get_text_embedding_batch([req.keyword for req in batch.requests])
    vector_strs = [
        "[" + ",".join(map(str, vec)) + "]"
        for vec in vectors
    ]

    # N 个独立查询并发执行，每个走 HNSW 索引
    results: dict[str, list[tuple[str, str, str, str]]] = {}
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
) -> dict[str, list[tuple[str, str, str, str]]]:
    results: dict[str, list[tuple[str, str, str, str]]] = {}
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
) -> dict[str, list[tuple[str, str, str, str]]]:
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
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_tsquery_sql(
            input_values=input_values,
            tsvector_column=column_name,
            order_expr="score DESC",
            type_filter=type_filter,
        )
        params["per_kw_limit"] = top_k * 3

    params["min_score"] = _BM25_MIN_SCORE
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    statement: Any = sql
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())


def _run_substring_query(
    session: Session,
    requests: list[RecallRequest],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
    per_type_limit: int = 0,
) -> dict[str, list[tuple[str, str, str, str]]]:
    input_values, params = _build_values_clause(
        requests,
        value_getter=lambda request: request.keyword,
    )
    if per_type_limit > 0:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
            per_type_limit=per_type_limit,
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
        )
        params["per_kw_limit"] = top_k * 3
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    statement: Any = sql
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())



# ---------------------------------------------------------------------------
# Single-vector query (HNSW-friendly: ORDER BY embedding <=> :constant LIMIT k)
# ---------------------------------------------------------------------------

_VECTOR_NORMAL_SQL = text(f"""
    SELECT tn.term_id,
           tn.name_text AS term_name,
           tn.name_id,
           t.term_type_code,
           1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score
    FROM {_SCHEMA}.term_name tn
    JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
    WHERE tn.name_embedding IS NOT NULL
    ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
    LIMIT :limit
""")  # noqa: S608

_VECTOR_TYPED_SQL = text(f"""
    SELECT tn.term_id,
           tn.name_text AS term_name,
           tn.name_id,
           t.term_type_code,
           1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score
    FROM {_SCHEMA}.term_name tn
    JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
    WHERE tn.name_embedding IS NOT NULL
      AND t.term_type_code IN :type_codes
    ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
    LIMIT :limit
""").bindparams(bindparam("type_codes", expanding=True))  # noqa: S608

_VECTOR_PER_TYPE_SQL = text(f"""
    SELECT term_id, term_name, name_id, term_type_code, score
    FROM (
        SELECT top_n.term_id,
               top_n.term_name,
               top_n.name_id,
               top_n.term_type_code,
               top_n.score,
               ROW_NUMBER() OVER (
                 PARTITION BY top_n.term_type_code
                 ORDER BY top_n.score DESC
               ) AS rn
        FROM (
            SELECT tn.term_id,
                   tn.name_text AS term_name,
                   tn.name_id,
                   t.term_type_code,
                   1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score
            FROM {_SCHEMA}.term_name tn
            JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
            WHERE tn.name_embedding IS NOT NULL
              AND t.term_type_code IN :type_codes
            ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
            LIMIT :limit
        ) top_n
    ) ranked
    WHERE rn <= :per_type_limit AND score >= :min_similarity
    ORDER BY score DESC
""").bindparams(bindparam("type_codes", expanding=True))  # noqa: S608


def _run_single_vector_query(
    req: RecallRequest,
    vector_str: str,
    *,
    top_k: int,
    min_similarity: float,
) -> dict[str, list[tuple[str, str, str, str]]]:
    """\u5355 keyword \u5411\u91cf\u67e5\u8be2\uff0c\u4f7f\u7528 HNSW \u7d22\u5f15 (ORDER BY <=> :constant LIMIT k)\u3002"""
    with get_session() as session:
        params: dict[str, Any] = {
            "vector": vector_str,
            "min_similarity": min_similarity,
        }
        if req.is_per_type and req.type_filter is not None:
            sql: Any = _VECTOR_PER_TYPE_SQL
            params["type_codes"] = sorted(req.type_filter)
            params["per_type_limit"] = req.per_type_limit
            params["limit"] = top_k * 3 * len(req.type_filter)
        elif req.type_filter is not None:
            sql = _VECTOR_TYPED_SQL
            params["type_codes"] = sorted(req.type_filter)
            params["limit"] = top_k * 3
        else:
            sql = _VECTOR_NORMAL_SQL
            params["limit"] = top_k * 3

        rows = session.execute(sql, params).fetchall()
        results: list[tuple[str, str, str, str]] = []
        for term_id, term_name, name_id, term_type_code, score in rows:
            if float(score) >= min_similarity:
                results.append(
                    (str(term_id), str(term_name), str(name_id), str(term_type_code))
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
) -> object:
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n            AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            )
            SELECT i.keyword_key, s.term_id, s.term_name, s.name_id, s.term_type_code, s.score
            FROM input i
            CROSS JOIN LATERAL (
              SELECT term_id, term_name, name_id, term_type_code, score
              FROM (
                SELECT tn.term_id,
                       tn.name_text AS term_name,
                       tn.name_id,
                       t.term_type_code,
                       ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.term_type_code
                         ORDER BY ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) DESC
                       ) AS rn
                FROM {_SCHEMA}.term_name tn
                JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
                WHERE tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
                  AND tn.{tsvector_column} IS NOT NULL{type_clause}
              ) ranked
              WHERE ranked.rn <= :per_type_limit AND ranked.score >= :min_score
            ) s
            ORDER BY i.keyword_key, s.score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            )
            SELECT i.keyword_key, s.term_id, s.term_name, s.name_id, s.term_type_code, s.score
            FROM input i
            CROSS JOIN LATERAL (
              SELECT tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score
              FROM {_SCHEMA}.term_name tn
              JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
              WHERE tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
                AND tn.{tsvector_column} IS NOT NULL{type_clause}
                AND ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) >= :min_score
              ORDER BY {order_expr}
              LIMIT :per_kw_limit
            ) s
            ORDER BY i.keyword_key, s.score DESC
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
) -> object:
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n                  AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            )
            SELECT i.keyword_key, s.term_id, s.term_name, s.name_id, s.term_type_code, s.score
            FROM input i
            CROSS JOIN LATERAL (
              SELECT term_id, term_name, name_id, term_type_code, score
              FROM (
                SELECT tn.term_id,
                       tn.name_text AS term_name,
                       tn.name_id,
                       t.term_type_code,
                       LENGTH(tn.name_text)::float AS score,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.term_type_code
                         ORDER BY LENGTH(tn.name_text) DESC
                       ) AS rn
                FROM {_SCHEMA}.term_name tn
                JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
                WHERE (
                        POSITION(tn.name_text IN i.keyword_text) > 0
                        OR POSITION(i.keyword_text IN tn.name_text) > 0
                      ){type_clause}
              ) ranked
              WHERE ranked.rn <= :per_type_limit
            ) s
            ORDER BY i.keyword_key, s.score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            )
            SELECT i.keyword_key, s.term_id, s.term_name, s.name_id, s.term_type_code, s.score
            FROM input i
            CROSS JOIN LATERAL (
              SELECT tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     LENGTH(tn.name_text)::float AS score
              FROM {_SCHEMA}.term_name tn
              JOIN {_SCHEMA}.term t ON tn.term_id = t.term_id
              WHERE (
                      POSITION(tn.name_text IN i.keyword_text) > 0
                      OR POSITION(i.keyword_text IN tn.name_text) > 0
                    ){type_clause}
              ORDER BY LENGTH(tn.name_text) DESC
              LIMIT :per_kw_limit
            ) s
            ORDER BY i.keyword_key, s.score DESC
        """
        sql_obj = text(sql)

    if type_filter is not None:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj

def _collect_ranked_rows(rows: Any) -> dict[str, list[tuple[str, str, str, str]]]:
    grouped: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for keyword_key, term_id, term_name, name_id, term_type_code, _score in rows:
        grouped[str(keyword_key)].append(
            (str(term_id), str(term_name), str(name_id), str(term_type_code))
        )
    return dict(grouped)


def _shape_diversified_candidates(
    diversified: list[tuple[str, str, str, str]],
    fused: list[Any],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
) -> list[CandidateDict]:
    score_map = {candidate.term_id: candidate.rrf_score for candidate in fused}
    candidates: list[CandidateDict] = []
    for term_id, term_name, name_id, term_type_code in diversified:
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
            }
        )
        if len(candidates) >= top_k:
            break
    return candidates
