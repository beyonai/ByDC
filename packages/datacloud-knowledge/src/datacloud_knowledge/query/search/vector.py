"""向量搜索实现。

使用 PostgreSQL pgvector 扩展的 HNSW 索引进行向量相似度搜索。
术语名称的向量存储在 name_embedding 字段中（1024 维）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from datacloud_knowledge.query.search.vector_validation import (
    TermVectorValidationError,
    validate_term_vector_readiness,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datacloud_knowledge.embedding import EmbeddingService

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VectorResult:
    """向量搜索结果。

    Attributes:
        term_id: 术语 ID
        term_name: 术语名称
        name_id: 名称 ID
        term_type_code: 术语类型代码
        similarity: 相似度分数 (0-1)
        term_code: 术语编码
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    similarity: float
    term_code: str = ""


def vector_search(
    session: Session,
    query_text: str,
    embedding_service: EmbeddingService,
    top_k: int = 10,
    min_similarity: float = 0.5,
) -> list[VectorResult]:
    """使用向量相似度搜索术语名称。

    将查询文本转换为向量，使用余弦距离搜索最相似的术语。

    Args:
        session: SQLAlchemy Session
        query_text: 查询文本
        embedding_service: Embedding 服务
        top_k: 返回结果数量上限
        min_similarity: 最小相似度阈值 (0-1)

    Returns:
        VectorResult 列表，按相似度降序排列
    """
    if not query_text or not query_text.strip():
        return []

    try:
        validate_term_vector_readiness(session, embedding_service)
    except TermVectorValidationError as exc:
        log.error("知识库向量校验失败，vector_search 返回空结果: %s", exc)
        return []

    # 获取查询向量
    query_vector = embedding_service.get_text_embedding(query_text.strip())
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"

    sql = text("""
        SELECT
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS similarity,
            t.term_code
        FROM
            term_name tn,
            term t
        WHERE
            tn.name_embedding IS NOT NULL
            AND tn.term_id = t.term_id
        ORDER BY
            tn.name_embedding <=> CAST(:vector AS vector)
        LIMIT :limit
    """)

    try:
        result = session.execute(sql, {"vector": vector_str, "limit": top_k})
        rows = result.fetchall()

        results: list[VectorResult] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, similarity, term_code = row
            if similarity >= min_similarity:
                results.append(
                    VectorResult(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        similarity=float(similarity),
                        term_code=str(term_code) if term_code else "",
                    )
                )

        log.debug("Vector search '%s' found %d results", query_text, len(results))
        return results

    except Exception as e:
        log.error("Vector search failed: %s", e)
        raise


def vector_search_by_vector(
    session: Session,
    query_vector: list[float],
    top_k: int = 10,
    min_similarity: float = 0.5,
) -> list[VectorResult]:
    """使用预计算的向量进行搜索。

    Args:
        session: SQLAlchemy Session
        query_vector: 查询向量
        top_k: 返回结果数量上限
        min_similarity: 最小相似度阈值 (0-1)

    Returns:
        VectorResult 列表，按相似度降序排列
    """
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"

    sql = text("""
        SELECT
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS similarity,
            t.term_code
        From
            term_name tn,
            term t
        WHERE
            tn.name_embedding IS NOT NULL
            AND tn.term_id = t.term_id
        ORDER BY
            tn.name_embedding <=> CAST(:vector AS vector)
        LIMIT :limit
    """)

    try:
        result = session.execute(sql, {"vector": vector_str, "limit": top_k})
        rows = result.fetchall()

        results: list[VectorResult] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, similarity, term_code = row
            if similarity >= min_similarity:
                results.append(
                    VectorResult(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        similarity=float(similarity),
                        term_code=str(term_code) if term_code else "",
                    )
                )

        return results

    except Exception as e:
        log.error("Vector search failed: %s", e)
        raise
