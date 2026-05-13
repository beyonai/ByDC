"""知识检索引擎 — 术语查找、别名消歧、全文召回。

提供术语检索的完整业务逻辑层，依赖 adapters/ 层的后端实现：
- term_search: 类型化术语搜索、字段别名消歧
- rrf: Reciprocal Rank Fusion 融合算法
- dimension_values: 维度值辅助识别
- tokenizers/: 中英文分词器
- embedding/: 向量嵌入服务
"""

from .dimension_values import DimensionValueResolver
from .owl_relation_resolver import resolve_related_owl_terms
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
    "RRFCandidate",
    "get_object_props",
    "get_prop_enum_values",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "resolve_field_aliases",
    "resolve_field_aliases_with_names",
    "resolve_related_owl_terms",
    "resolve_value_aliases",
    "rrf_fuse",
    "search_terms_by_type",
]
