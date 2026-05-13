"""公共 API 层 — 协议、类型、分词器接口。

api/ 是 datacloud-knowledge 的基础抽象层，提供：
- 协议接口：TermReader、TermSearchEngine、TermWriter、Tokenizer、StopwordProvider
- 共享类型：术语查询结果、别名消歧结果、搜索召回结果、写入操作类型
- 无外部副作用依赖（不引用 DB 连接、SQLAlchemy 等）
"""

from .protocols import TermReader, TermSearchEngine, TermWriter
from .text import StopwordProvider, Tokenizer
from .types import (
    AmbiguousCandidate,
    BM25Result,
    ClarificationMode,
    FieldResolutionResult,
    FieldResolutionResultWithNames,
    NameItem,
    OpaquePayload,
    OwlResolveRoot,
    PropItem,
    ResolvedField,
    SearchTermsResult,
    SubstringResult,
    TagFilter,
    TagOp,
    TagValueType,
    TermBrief,
    TermItem,
    TermNameCreate,
    ValueResolutionResult,
    ValueWithAliases,
    VectorResult,
)

__all__ = [
    "AmbiguousCandidate",
    "BM25Result",
    "ClarificationMode",
    "FieldResolutionResult",
    "FieldResolutionResultWithNames",
    "NameItem",
    "OpaquePayload",
    "OwlResolveRoot",
    "PropItem",
    "ResolvedField",
    "SearchTermsResult",
    "StopwordProvider",
    "SubstringResult",
    "TagFilter",
    "TagOp",
    "TagValueType",
    "TermBrief",
    "TermItem",
    "TermNameCreate",
    "TermReader",
    "TermSearchEngine",
    "TermWriter",
    "Tokenizer",
    "ValueResolutionResult",
    "ValueWithAliases",
    "VectorResult",
]
