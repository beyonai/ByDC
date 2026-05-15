"""BM25 搜索实现。

使用 PostgreSQL 的 tsvector + ts_rank_cd 实现 BM25 风格的全文搜索。
术语名称使用单字分词，存储在 name_keywords 字段中。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text
from sqlalchemy.sql.elements import TextClause

from datacloud_knowledge.adapters.opengauss._db.url import resolve_knowledge_schema

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_COLUMN_CAPS_CACHE: dict[str, bool] = {}

_TABLE = "term_name"
_TSV_COLUMN = "name_keywords"


@dataclass(frozen=True, slots=True)
class BM25Result:
    """单条 BM25 匹配结果。"""

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    score: float
    term_code: str = ""


def _rollback_quietly(session: Session) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        with suppress(Exception):
            rollback()


def _has_name_keywords_column(session: Session) -> bool:
    schema = resolve_knowledge_schema()
    cache_key = f"{schema}.name_keywords"
    cached = _COLUMN_CAPS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    sql = text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :table_schema
          AND table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
        """
    )
    try:
        rows = session.execute(
            sql,
            {
                "table_schema": schema,
                "table_name": _TABLE,
                "column_name": _TSV_COLUMN,
            },
        ).fetchall()
        _COLUMN_CAPS_CACHE[cache_key] = bool(rows)
    except Exception as exc:
        _rollback_quietly(session)
        log.warning("BM25 column capability check failed, fallback to expression mode: %s", exc)
        _COLUMN_CAPS_CACHE[cache_key] = False

    return bool(_COLUMN_CAPS_CACHE[cache_key])


def _build_search_sql(*, with_type_filter: bool = False) -> TextClause:
    type_clause = "\n            AND t.term_type_code IN :type_codes" if with_type_filter else ""
    sql_text = f"""
        SELECT
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            ts_rank_cd(tn.name_keywords, query, 32) AS score,
            t.term_code
        FROM
            term_name tn,
            term t,
            to_tsquery('simple', :tsquery) query
        WHERE
            tn.name_keywords @@ query
            AND tn.term_id = t.term_id
            AND tn.name_keywords IS NOT NULL{type_clause}
        ORDER BY
            score DESC
        LIMIT :limit
    """
    if with_type_filter:
        return text(sql_text).bindparams(
            bindparam("type_codes", expanding=True),
        )
    return text(sql_text)


def _run_search(
    session: Session,
    *,
    tsquery: str,
    top_k: int,
    min_score: float,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    sql = _build_search_sql(with_type_filter=term_type_codes is not None)
    params: dict[str, Any] = {"tsquery": tsquery, "limit": top_k}
    if term_type_codes is not None:
        params["type_codes"] = sorted(term_type_codes)
    rows = session.execute(sql, params).fetchall()
    return [
        BM25Result(
            term_id=term_id,
            term_name=term_name,
            name_id=name_id,
            term_type_code=term_type_code,
            score=float(score),
            term_code=str(term_code) if term_code else "",
        )
        for term_id, term_name, name_id, term_type_code, score, term_code in rows
        if score >= min_score
    ]


def _search(
    session: Session,
    query_text: str,
    *,
    ts_operator: str,
    top_k: int,
    min_score: float,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    if not query_text or not query_text.strip():
        return []

    tsquery = f" {ts_operator} ".join(list(query_text.strip()))
    if not _has_name_keywords_column(session):
        message = (
            "BM25 requires term_name.name_keywords column. "
            "Please apply DDL/importer to populate this column before querying."
        )
        log.error(message)
        raise RuntimeError(message)

    try:
        return _run_search(
            session,
            tsquery=tsquery,
            top_k=top_k,
            min_score=min_score,
            term_type_codes=term_type_codes,
        )
    except Exception:
        _rollback_quietly(session)
        log.exception("BM25 search failed")
        raise


def bm25_search(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.01,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """使用 BM25 搜索术语名称（AND 语义，所有字符必须匹配）。"""
    return _search(
        session,
        query_text,
        ts_operator="&",
        top_k=top_k,
        min_score=min_score,
        term_type_codes=term_type_codes,
    )


def bm25_search_with_or(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.01,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """使用 BM25 搜索术语名称（OR 语义，匹配任意字符即可）。"""
    return _search(
        session,
        query_text,
        ts_operator="|",
        top_k=top_k,
        min_score=min_score,
        term_type_codes=term_type_codes,
    )


def _build_partitioned_search_sql(*, with_type_filter: bool = True) -> TextClause:
    """BM25 查询 + ``ROW_NUMBER() OVER (PARTITION BY term_type_code)`` 分区取 top-N。"""
    sql_text = """
        SELECT term_id, term_name, name_id, term_type_code, score, term_code
        FROM (
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                ts_rank_cd(tn.name_keywords, query, 32) AS score,
                ROW_NUMBER() OVER (
                    PARTITION BY t.term_type_code
                    ORDER BY ts_rank_cd(tn.name_keywords, query, 32) DESC
                ) AS rn,
                t.term_code
            FROM
                term_name tn,
                term t,
                to_tsquery('simple', :tsquery) query
            WHERE
                tn.name_keywords @@ query
                AND tn.term_id = t.term_id
                AND tn.name_keywords IS NOT NULL
                AND t.term_type_code IN :type_codes
        ) ranked
        WHERE rn <= :per_type_limit
        ORDER BY score DESC
    """
    return text(sql_text).bindparams(
        bindparam("type_codes", expanding=True),
    )


def _run_partitioned_search(
    session: Session,
    *,
    tsquery: str,
    per_type_limit: int,
    min_score: float,
    term_type_codes: set[str],
) -> list[BM25Result]:
    """BM25 查询，按 term_type_code 分区取 top per_type_limit。"""
    sql = _build_partitioned_search_sql()
    params: dict[str, Any] = {
        "tsquery": tsquery,
        "type_codes": sorted(term_type_codes),
        "per_type_limit": per_type_limit,
    }
    rows = session.execute(sql, params).fetchall()
    return [
        BM25Result(
            term_id=term_id,
            term_name=term_name,
            name_id=name_id,
            term_type_code=term_type_code,
            score=float(score),
            term_code=str(term_code) if term_code else "",
        )
        for term_id, term_name, name_id, term_type_code, score, term_code in rows
        if score >= min_score
    ]


def bm25_search_partitioned(
    session: Session,
    query_text: str,
    per_type_limit: int = 3,
    min_score: float = 0.001,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """按 type_code 分区取 top-N 的 BM25 AND 搜索。"""
    if not query_text or not query_text.strip() or not term_type_codes:
        return []
    tsquery = " & ".join(list(query_text.strip()))
    if not _has_name_keywords_column(session):
        return []
    try:
        return _run_partitioned_search(
            session,
            tsquery=tsquery,
            per_type_limit=per_type_limit,
            min_score=min_score,
            term_type_codes=term_type_codes,
        )
    except Exception:
        _rollback_quietly(session)
        log.exception("BM25 partitioned search failed")
        raise


def bm25_search_with_or_partitioned(
    session: Session,
    query_text: str,
    per_type_limit: int = 3,
    min_score: float = 0.001,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """按 type_code 分区取 top-N 的 BM25 OR 搜索。"""
    if not query_text or not query_text.strip() or not term_type_codes:
        return []
    tsquery = " | ".join(list(query_text.strip()))
    if not _has_name_keywords_column(session):
        return []
    try:
        return _run_partitioned_search(
            session,
            tsquery=tsquery,
            per_type_limit=per_type_limit,
            min_score=min_score,
            term_type_codes=term_type_codes,
        )
    except Exception:
        _rollback_quietly(session)
        log.exception("BM25 partitioned OR search failed")
        raise


# ── jieba 词级 BM25 搜索（使用 name_keywords_jieba 列）──────────────


_JIEBA_COLUMN_CACHE: dict[str, bool] = {}


def _has_jieba_column(session: Session) -> bool:
    """name_keywords_jieba 列是否存在。"""
    schema = resolve_knowledge_schema()
    cache_key = f"{schema}.name_keywords_jieba"
    cached = _JIEBA_COLUMN_CACHE.get(cache_key)
    if cached is not None:
        return cached
    sql = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = :table_schema "
        "AND table_name = :table_name "
        "AND column_name = :column_name"
    )
    try:
        rows = session.execute(
            sql,
            {
                "table_schema": schema,
                "table_name": _TABLE,
                "column_name": "name_keywords_jieba",
            },
        ).fetchall()
        _JIEBA_COLUMN_CACHE[cache_key] = bool(rows)
    except Exception as exc:
        _rollback_quietly(session)
        log.warning("jieba column check failed, disabling: %s", exc)
        _JIEBA_COLUMN_CACHE[cache_key] = False
    return bool(_JIEBA_COLUMN_CACHE[cache_key])


def _jieba_tokenize(text_input: str) -> str:
    """jieba 分词后用 `` & `` 拼接为 tsquery 字符串。"""
    try:
        import jieba
    except ImportError:
        return " & ".join(list(text_input.strip()))
    tokens = [t for t in jieba.lcut(text_input) if t.strip()]
    if not tokens:
        return " & ".join(list(text_input.strip()))
    return " & ".join(tokens)


def _build_jieba_search_sql(*, with_type_filter: bool = False) -> TextClause:
    """BM25 查询 name_keywords_jieba 列。"""
    type_clause = "\n            AND t.term_type_code IN :type_codes" if with_type_filter else ""
    sql_text = f"""
        SELECT
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            ts_rank_cd(tn.name_keywords_jieba, query, 32) AS score,
            t.term_code
        FROM
            term_name tn,
            term t,
            to_tsquery('simple', :tsquery) query
        WHERE
            tn.name_keywords_jieba @@ query
            AND tn.term_id = t.term_id
            AND tn.name_keywords_jieba IS NOT NULL{type_clause}
        ORDER BY
            score DESC
        LIMIT :limit
    """
    if with_type_filter:
        return text(sql_text).bindparams(
            bindparam("type_codes", expanding=True),
        )
    return text(sql_text)


def _run_jieba_search(
    session: Session,
    *,
    tsquery: str,
    top_k: int,
    min_score: float,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    sql = _build_jieba_search_sql(with_type_filter=term_type_codes is not None)
    params: dict[str, Any] = {"tsquery": tsquery, "limit": top_k}
    if term_type_codes is not None:
        params["type_codes"] = sorted(term_type_codes)
    rows = session.execute(sql, params).fetchall()
    return [
        BM25Result(
            term_id=term_id,
            term_name=term_name,
            name_id=name_id,
            term_type_code=term_type_code,
            score=float(score),
            term_code=str(term_code) if term_code else "",
        )
        for term_id, term_name, name_id, term_type_code, score, term_code in rows
        if score >= min_score
    ]


def bm25_search_jieba(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.001,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """词级 BM25 AND 搜索（查询 name_keywords_jieba 列）。

    将输入文本 jieba 分词后构造 AND tsquery，与 DB 侧的
    jieba 分词 tsvector 做词级匹配。
    """
    if not query_text or not query_text.strip():
        return []
    if not _has_jieba_column(session):
        return []
    tsquery = _jieba_tokenize(query_text)
    if not tsquery:
        return []
    try:
        return _run_jieba_search(
            session,
            tsquery=tsquery,
            top_k=top_k,
            min_score=min_score,
            term_type_codes=term_type_codes,
        )
    except Exception:
        _rollback_quietly(session)
        log.exception("BM25 jieba search failed for '%s'", query_text)
        raise


def _build_jieba_partitioned_sql() -> TextClause:
    """jieba 分词 BM25 + PARTITION BY term_type_code 分区取 top-N。"""
    sql_text = """
        SELECT term_id, term_name, name_id, term_type_code, score, term_code
        FROM (
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                ts_rank_cd(tn.name_keywords_jieba, query, 32) AS score,
                ROW_NUMBER() OVER (
                    PARTITION BY t.term_type_code
                    ORDER BY ts_rank_cd(tn.name_keywords_jieba, query, 32) DESC
                ) AS rn,
                t.term_code
            FROM
                term_name tn,
                term t,
                to_tsquery('simple', :tsquery) query
            WHERE
                tn.name_keywords_jieba @@ query
                AND tn.term_id = t.term_id
                AND tn.name_keywords_jieba IS NOT NULL
                AND t.term_type_code IN :type_codes
        ) ranked
        WHERE rn <= :per_type_limit
        ORDER BY score DESC
    """
    return text(sql_text).bindparams(
        bindparam("type_codes", expanding=True),
    )


def bm25_search_jieba_partitioned(
    session: Session,
    query_text: str,
    per_type_limit: int = 3,
    min_score: float = 0.001,
    term_type_codes: set[str] | None = None,
) -> list[BM25Result]:
    """词级 BM25 AND + 按 type_code 分区取 top-N。"""
    if not query_text or not query_text.strip() or not term_type_codes:
        return []
    if not _has_jieba_column(session):
        return []
    tsquery = _jieba_tokenize(query_text)
    if not tsquery:
        return []
    sql = _build_jieba_partitioned_sql()
    params: dict[str, Any] = {
        "tsquery": tsquery,
        "type_codes": sorted(term_type_codes),
        "per_type_limit": per_type_limit,
    }
    try:
        rows = session.execute(sql, params).fetchall()
        return [
            BM25Result(
                term_id=term_id,
                term_name=term_name,
                name_id=name_id,
                term_type_code=term_type_code,
                score=float(score),
                term_code=str(term_code) if term_code else "",
            )
            for term_id, term_name, name_id, term_type_code, score, term_code in rows
            if score >= min_score
        ]
    except Exception:
        _rollback_quietly(session)
        log.exception("BM25 jieba partitioned search failed")
        raise
