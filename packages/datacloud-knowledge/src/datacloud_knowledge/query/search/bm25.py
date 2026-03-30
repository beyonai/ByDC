"""BM25 搜索实现。

使用 PostgreSQL 的 tsvector + ts_rank_cd 实现 BM25 风格的全文搜索。
术语名称使用单字分词，存储在 name_keywords 字段中。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BM25Result:
    """BM25 搜索结果。

    Attributes:
        term_id: 术语 ID
        term_name: 术语名称
        name_id: 名称 ID
        term_type_code: 术语类型代码
        score: BM25 分数
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    score: float


def bm25_search(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.01,
) -> list[BM25Result]:
    """使用 BM25 搜索术语名称。

    使用 PostgreSQL 的 ts_rank_cd 进行 BM25 风格的全文搜索。
    查询文本会被转换为单字分词格式进行匹配。

    Args:
        session: SQLAlchemy Session
        query_text: 查询文本
        top_k: 返回结果数量上限
        min_score: 最小分数阈值

    Returns:
        BM25Result 列表，按分数降序排列
    """
    if not query_text or not query_text.strip():
        return []

    # 将查询文本转换为单字分词格式（空格分隔）
    query_tokens = " ".join(list(query_text.strip()))
    # 构建 tsquery 格式（AND 连接）
    tsquery = " & ".join(list(query_text.strip()))

    sql = text("""
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
    """)

    try:
        result = session.execute(sql, {"tsquery": tsquery, "limit": top_k})
        rows = result.fetchall()

        results: list[BM25Result] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, score = row
            if score >= min_score:
                results.append(
                    BM25Result(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        score=float(score),
                    )
                )

        log.debug("BM25 search '%s' found %d results", query_text, len(results))
        return results

    except Exception as e:
        log.error("BM25 search failed: %s", e)
        raise


def bm25_search_with_or(
    session: Session,
    query_text: str,
    top_k: int = 10,
    min_score: float = 0.01,
) -> list[BM25Result]:
    """使用 BM25 搜索术语名称（OR 模式）。

    使用 OR 连接查询词，匹配任意一个字符即可。

    Args:
        session: SQLAlchemy Session
        query_text: 查询文本
        top_k: 返回结果数量上限
        min_score: 最小分数阈值

    Returns:
        BM25Result 列表，按分数降序排列
    """
    if not query_text or not query_text.strip():
        return []

    # 构建 tsquery 格式（OR 连接）
    tsquery = " | ".join(list(query_text.strip()))

    sql = text("""
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
    """)

    try:
        result = session.execute(sql, {"tsquery": tsquery, "limit": top_k})
        rows = result.fetchall()

        results: list[BM25Result] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, score = row
            if score >= min_score:
                results.append(
                    BM25Result(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        score=float(score),
                    )
                )

        return results

    except Exception as e:
        log.error("BM25 search failed: %s", e)
        raise
