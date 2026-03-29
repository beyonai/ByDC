"""搜索模块 — BM25 全文搜索 + 向量语义搜索。

提供两种搜索模式：
1. BM25: 基于 tsvector 的全文搜索，使用单字分词
2. Vector: 基于 pgvector 的向量语义搜索

使用方式：
    from datacloud_knowledge.query.search import bm25_search, vector_search, BM25Result, VectorResult

    # BM25 搜索
    results = bm25_search(session, "企业分析", top_k=10)

    # 向量搜索
    from datacloud_knowledge.query.embedding import get_embedding_service
    results = vector_search(session, "企业分析", get_embedding_service(), top_k=10)
"""

from datacloud_knowledge.query.search.bm25 import (
    BM25Result,
    bm25_search,
    bm25_search_with_or,
)
from datacloud_knowledge.query.search.vector import (
    VectorResult,
    vector_search,
    vector_search_by_vector,
)

__all__ = [
    "BM25Result",
    "VectorResult",
    "bm25_search",
    "bm25_search_with_or",
    "vector_search",
    "vector_search_by_vector",
]
