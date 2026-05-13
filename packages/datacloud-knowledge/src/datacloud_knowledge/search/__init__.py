"""搜索模块 — 术语检索、维度值解析、多路召回融合。

提供：
1. 术语检索（PostgresTermReader）：按类型、关键词、标签检索术语
2. 维度值解析（DimensionValueResolver）：动态枚举值加载
3. OWL 关系解析（resolve_related_owl_terms）：OWL 术语图遍历
4. 字段/值别名消歧（resolve_field_aliases 等）：精确匹配
5. 多路召回：BM25、向量、子串、分词 + RRF 融合

使用方式：
    from datacloud_knowledge.search import (
        PostgresTermReader,
        DimensionValueResolver,
        bm25_search,
        vector_search,
        rrf_fuse,
    )
"""

from __future__ import annotations

from .bm25 import (
    BM25Result,
    bm25_search,
    bm25_search_with_or,
)
from .dimension_values import DimensionValueResolver
from .jieba_recall import jieba_recall
from .owl_relation_resolver import resolve_related_owl_terms
from .rrf import RRFCandidate, rrf_fuse
from .search_engine import PostgresSearchEngine
from .substring_recall import substring_recall
from .term_reader import PostgresTermReader
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
from .types import (
    AmbiguousCandidate,
    FieldResolutionResult,
    FieldResolutionResultWithNames,
    ResolvedField,
    ValueResolutionResult,
)
from .vector import (
    VectorResult,
    vector_search,
    vector_search_by_vector,
)

__all__ = [
    "AmbiguousCandidate",
    "BM25Result",
    "DimensionValueResolver",
    "FieldResolutionResult",
    "FieldResolutionResultWithNames",
    "PostgresSearchEngine",
    "PostgresTermReader",
    "RRFCandidate",
    "ResolvedField",
    "ValueResolutionResult",
    "VectorResult",
    "bm25_search",
    "bm25_search_with_or",
    "get_object_props",
    "get_prop_enum_values",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "jieba_recall",
    "resolve_field_aliases",
    "resolve_field_aliases_with_names",
    "resolve_related_owl_terms",
    "resolve_value_aliases",
    "rrf_fuse",
    "search_terms_by_type",
    "substring_recall",
    "vector_search",
    "vector_search_by_vector",
]
