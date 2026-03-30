"""鍚戦噺鎼滅储瀹炵幇銆?

浣跨敤 PostgreSQL pgvector 鎵╁睍鐨?HNSW 绱㈠紩杩涜鍚戦噺鐩镐技搴︽悳绱€?
鏈鍚嶇О鐨勫悜閲忓瓨鍌ㄥ湪 name_embedding 瀛楁涓紙1024 缁达級銆?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datacloud_knowledge.query.embedding import EmbeddingService

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VectorResult:
    """鍚戦噺鎼滅储缁撴灉銆?

    Attributes:
        term_id: 鏈 ID
        term_name: 鏈鍚嶇О
        name_id: 鍚嶇О ID
        term_type_code: 鏈绫诲瀷浠ｇ爜
        similarity: 鐩镐技搴﹀垎鏁?(0-1)
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    similarity: float


def vector_search(
    session: Session,
    query_text: str,
    embedding_service: EmbeddingService,
    top_k: int = 10,
    min_similarity: float = 0.5,
) -> list[VectorResult]:
    """浣跨敤鍚戦噺鐩镐技搴︽悳绱㈡湳璇悕绉般€?

    灏嗘煡璇㈡枃鏈浆鎹负鍚戦噺锛屼娇鐢ㄤ綑寮﹁窛绂绘悳绱㈡渶鐩镐技鐨勬湳璇€?

    Args:
        session: SQLAlchemy Session
        query_text: 鏌ヨ鏂囨湰
        embedding_service: Embedding 鏈嶅姟
        top_k: 杩斿洖缁撴灉鏁伴噺涓婇檺
        min_similarity: 鏈€灏忕浉浼煎害闃堝€?(0-1)

    Returns:
        VectorResult 鍒楄〃锛屾寜鐩镐技搴﹂檷搴忔帓鍒?
    """
    if not query_text or not query_text.strip():
        return []

    # 鑾峰彇鏌ヨ鍚戦噺
    query_vector = embedding_service.get_text_embedding(query_text.strip())
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"

    sql = text("""
        SELECT 
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            1 - (tn.name_embedding <=> :vector::vector) AS similarity
        FROM 
            whale_datacloud.term_name tn,
            whale_datacloud.term t
        WHERE 
            tn.name_embedding IS NOT NULL
            AND tn.term_id = t.term_id
        ORDER BY 
            tn.name_embedding <=> :vector::vector
        LIMIT :limit
    """)

    try:
        result = session.execute(sql, {"vector": vector_str, "limit": top_k})
        rows = result.fetchall()

        results: list[VectorResult] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, similarity = row
            if similarity >= min_similarity:
                results.append(
                    VectorResult(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        similarity=float(similarity),
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
    """浣跨敤棰勮绠楃殑鍚戦噺杩涜鎼滅储銆?

    Args:
        session: SQLAlchemy Session
        query_vector: 鏌ヨ鍚戦噺
        top_k: 杩斿洖缁撴灉鏁伴噺涓婇檺
        min_similarity: 鏈€灏忕浉浼煎害闃堝€?(0-1)

    Returns:
        VectorResult 鍒楄〃锛屾寜鐩镐技搴﹂檷搴忔帓鍒?
    """
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"

    sql = text("""
        SELECT 
            tn.term_id,
            tn.name_text AS term_name,
            tn.name_id,
            t.term_type_code,
            1 - (tn.name_embedding <=> :vector::vector) AS similarity
        FROM 
            whale_datacloud.term_name tn,
            whale_datacloud.term t
        WHERE 
            tn.name_embedding IS NOT NULL
            AND tn.term_id = t.term_id
        ORDER BY 
            tn.name_embedding <=> :vector::vector
        LIMIT :limit
    """)

    try:
        result = session.execute(sql, {"vector": vector_str, "limit": top_k})
        rows = result.fetchall()

        results: list[VectorResult] = []
        for row in rows:
            term_id, term_name, name_id, term_type_code, similarity = row
            if similarity >= min_similarity:
                results.append(
                    VectorResult(
                        term_id=term_id,
                        term_name=term_name,
                        name_id=name_id,
                        term_type_code=term_type_code,
                        similarity=float(similarity),
                    )
                )

        return results

    except Exception as e:
        log.error("Vector search failed: %s", e)
        raise

