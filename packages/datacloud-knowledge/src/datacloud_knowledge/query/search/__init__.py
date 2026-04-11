"""搜索模块 — BM25 全文搜索 + 向量语义搜索 + RRF 融合 + 子串/分词召回。

提供多种搜索模式：
1. BM25: 基于 tsvector 的全文搜索，使用单字分词
2. Vector: 基于 pgvector 的向量语义搜索
3. RRF: Reciprocal Rank Fusion 多路结果融合
4. Substring: 双向子串匹配召回
5. Jieba: 结巴分词 + 逐 token BM25 + RRF 内融合

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
from datacloud_knowledge.query.search.jieba_recall import jieba_recall
from datacloud_knowledge.query.search.rrf import RRFCandidate, rrf_fuse
from datacloud_knowledge.query.search.substring_recall import substring_recall
from datacloud_knowledge.query.search.vector import (
    VectorResult,
    vector_search,
    vector_search_by_vector,
)

__all__ = [
    "BM25Result",
    "RRFCandidate",
    "VectorResult",
    "bm25_search",
    "bm25_search_with_or",
    "jieba_recall",
    "rrf_fuse",
    "substring_recall",
    "vector_search",
    "vector_search_by_vector",
]
