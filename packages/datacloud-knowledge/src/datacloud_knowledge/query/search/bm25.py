"""BM25-style term name search over PostgreSQL/OpenGauss."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_COLUMN_CAPS_CACHE: dict[str, bool | None] = {"name_keywords": None}

_SCHEMA = "whale_datacloud"
_TABLE = "term_name"
_TSV_COLUMN = "name_keywords"


@dataclass(frozen=True, slots=True)
class BM25Result:
    """Single BM25 match row."""

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    score: float


def _rollback_quietly(session: Session) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        with suppress(Exception):
            rollback()


def _has_name_keywords_column(session: Session) -> bool:
    cached = _COLUMN_CAPS_CACHE["name_keywords"]
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
                "table_schema": _SCHEMA,
                "table_name": _TABLE,
                "column_name": _TSV_COLUMN,
            },
        ).fetchall()
        _COLUMN_CAPS_CACHE["name_keywords"] = bool(rows)
    except Exception as exc:
        _rollback_quietly(session)
        log.warning("BM25 column capability check failed, fallback to expression mode: %s", exc)
        _COLUMN_CAPS_CACHE["name_keywords"] = False

    return bool(_COLUMN_CAPS_CACHE["name_keywords"])


def _build_search_sql() -> object:
    return text(
        """
        SELECT
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            ts_rank_cd(tn.name_keywords, query, 32) AS score
        FROM
            whale_datacloud.term_name tn,
            whale_datacloud.term t,
            to_tsquery('simple', :tsquery) query
        WHERE
            tn.name_keywords @@ query
            AND tn.term_id = t.term_id
            AND tn.name_keywords IS NOT NULL
        ORDER BY
            score DESC
        LIMIT :limit
    """
    )


def _run_search(
    session: Session,
    *,
    tsquery: str,
    top_k: int,
    min_score: float,
) -> list[BM25Result]:
    sql = _build_search_sql()
    rows = session.execute(sql, {"tsquery": tsquery, "limit": top_k}).fetchall()
    return [
        BM25Result(
            term_id=term_id,
            term_name=term_name,
            name_id=name_id,
            term_type_code=term_type_code,
            score=float(score),
        )
        for term_id, term_name, name_id, term_type_code, score in rows
        if score >= min_score
    ]


def _search(
    session: Session,
    query_text: str,
    *,
    ts_operator: str,
    top_k: int,
    min_score: float,
) -> list[BM25Result]:
    if not query_text or not query_text.strip():
        return []

    tsquery = f" {ts_operator} ".join(list(query_text.strip()))
    if not _has_name_keywords_column(session):
        message = (
            "BM25 requires whale_datacloud.term_name.name_keywords column. "
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
) -> list[BM25Result]:
    """Search with AND semantics for every character token."""
    return _search(
        session,
        query_text,
        ts_operator="&",
        top_k=top_k,
        min_score=min_score,
    )


def bm25_search_with_or(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.01,
) -> list[BM25Result]:
    """Search with OR semantics for character tokens."""
    return _search(
        session,
        query_text,
        ts_operator="|",
        top_k=top_k,
        min_score=min_score,
    )

