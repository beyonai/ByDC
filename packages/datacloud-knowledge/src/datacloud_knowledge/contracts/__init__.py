"""接口契约层 — 定义 SDK 的所有协议和共享类型。

contracts/ 是 datacloud-knowledge 的基础抽象层，提供：
- 协议接口：TermReader、TermSearchEngine、TermWriter
- 分词协议：Tokenizer、StopwordProvider
- 共享类型：术语查询结果、别名消歧结果、搜索召回结果

所有后端实现（adapters/）必须实现此层的协议。
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
