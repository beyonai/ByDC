"""TermProvider 协议专用类型 — 重导出 capabilities/types.py。

从 capabilities/types.py 重导出所有共享类型。原定义已迁移至
capabilities/ 模块（零外部依赖，纯 dataclass），此处保留兼容性重导出。

参考: _Architecture Patterns with Python_ 第 1 章「领域模型独立」。
"""

from __future__ import annotations

from datacloud_knowledge.capabilities.types import (
    ImportResult,
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermItem,
    TermUpdate,
)

__all__ = [
    "ImportResult",
    "LabelCondition",
    "LabelFilter",
    "QueryResult",
    "QueryType",
    "TermCreate",
    "TermDetail",
    "TermItem",
    "TermUpdate",
]
