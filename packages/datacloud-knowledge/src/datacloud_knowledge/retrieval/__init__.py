"""知识检索引擎 — 术语查找、别名消歧、全文召回。

提供术语检索的完整业务逻辑层，依赖 adapters/ 层的后端实现：
- term_search: 类型化术语搜索、字段别名消歧
- mention_matching: Mention 级术语匹配（exact/rapidfuzz/bm25/vector）
- recall/: 多路批量召回（BM25 AND / jieba / 子串 / 向量） + RRF 融合
- rrf: Reciprocal Rank Fusion 融合算法
- dimension_values: 维度值辅助识别
- tokenizers/: 中英文分词器
- embedding/: 向量嵌入服务
"""

# BM25/向量搜索 — 从 adapters 层重导出，供 matching 等检索模块使用
from datacloud_knowledge.adapters.opengauss.bm25 import bm25_search
from datacloud_knowledge.adapters.opengauss.vector import vector_search

from .dimension_values import DimensionValueResolver
from .mention_matching import match_mentions, match_mentions_with_search
from .name_cache import UserNameCache
from .owl_relation_resolver import resolve_related_owl_terms
from .recall import PreparedBatch, RecallRequest, ScopeRecallLayer, typed_multi_recall_batch
from .rrf import RRFCandidate, rrf_fuse
from .term_search import (
    get_object_props,
    get_prop_enum_values,
    get_prop_values_with_aliases,
    get_term_ids,
    get_term_names,
    resolve_field_aliases,
    resolve_field_aliases_with_names,
    resolve_value_aliases,
    search_terms_by_type,
)

__all__ = [
    "DimensionValueResolver",
    "PreparedBatch",
    "RRFCandidate",
    "RecallRequest",
    "ScopeRecallLayer",
    "UserNameCache",
    "bm25_search",
    "get_object_props",
    "get_prop_enum_values",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "match_mentions",
    "match_mentions_with_search",
    "resolve_field_aliases",
    "resolve_field_aliases_with_names",
    "resolve_related_owl_terms",
    "resolve_value_aliases",
    "rrf_fuse",
    "search_terms_by_type",
    "typed_multi_recall_batch",
    "vector_search",
]
