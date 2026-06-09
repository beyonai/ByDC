"""知识检索引擎 — 术语查找、别名消歧、全文召回。

提供术语检索的完整业务逻辑层，所有函数注入 TermStore 实例：
- _patterns: Layer 1 查询组合模式（纯函数）
- term_search: 类型化术语搜索、降级编排
- field_resolution: 字段别名消歧
- enum_resolution: 枚举值查询
- mention_matching: Mention 级术语匹配（exact/rapidfuzz/bm25/vector）
- name_cache: 用户名称缓存
- dimension_values: 维度值辅助识别
- owl_relation_resolver: OWL 关系遍历
- tokenizers/: 中英文分词器
- embedding/: 向量嵌入服务
"""

from ._patterns import query_bound_values, query_scope_props, query_user_synonyms
from .dimension_values import DimensionValueResolver
from .enum_resolution import get_prop_enum_values
from .field_resolution import resolve_field_aliases
from .mention_matching import match_mentions, match_mentions_with_search
from .name_cache import UserNameCache
from .owl_relation_resolver import resolve_related_owl_terms

# 保留 rrf 兼容层导出（过渡期）
from .rrf import RRFCandidate, rrf_fuse
from .term_search import (
    get_object_props,
    get_object_props_by_code,
    get_prop_values_with_aliases,
    get_term_ids,
    get_term_names,
    resolve_value_aliases,
    search_terms_by_type,
    search_terms_with_fallback,
)

__all__ = [
    "DimensionValueResolver",
    "RRFCandidate",
    "UserNameCache",
    "get_object_props",
    "get_object_props_by_code",
    "get_prop_enum_values",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "match_mentions",
    "match_mentions_with_search",
    "query_bound_values",
    "query_scope_props",
    "query_user_synonyms",
    "resolve_field_aliases",
    "resolve_related_owl_terms",
    "resolve_value_aliases",
    "rrf_fuse",
    "search_terms_by_type",
    "search_terms_with_fallback",
]
