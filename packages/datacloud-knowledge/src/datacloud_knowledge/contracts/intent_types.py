"""Intent domain shared types — safe to import from both retrieval/ and intent/.

These types are extracted from intent/clarification/models.py to break the dependency
inversion that would occur when retrieval/ modules need to reference intent domain types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datacloud_knowledge.contracts.types import ResolvedField


# ── 术语提取 ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ExtractedTerm:
    """从结构中提取的单个中文术语。"""

    raw_text: str
    """原始文本，如 "营收"。"""

    ktype: str
    """召回类型：select | groupBy | whereKey | whereValue | orderBy。"""

    path: str
    """JSON pointer，如 "select.0" / "filters.1.field" / "metrics.2.expr"。"""

    source: Literal["main", "complex_condition"]
    """来源：主结构 or complex_condition。"""

    condition_index: int
    """complex_conditions 索引，主结构为 -1。"""

    search_enabled: bool = True
    """False → 跳过召回（纯数字/日期/非中文/别名引用）。"""

    vector_only: bool = False
    """True → 只走向量召回（英文标识符如 stat_date，文本匹配无意义）。"""

    parent_raw_text: str | None = None
    """别名扩展词的父术语。如 "地块名称" 的 parent 是 "地块"。原始词为 None。"""


# ── Pre-Resolve ──────────────────────────────────────────────────────


@dataclass
class PreResolveResult:
    """pre_resolve 阶段的输出。

    所有字典以 ``path:raw_text`` 复合键（如 ``filters.0.field:效能``）为键，
    确保同一 path 下不同 raw_text 的术语不会互相覆盖，
    同时保持与下游 path 格式的兼容性。
    """

    confirmed: dict[str, ResolvedField]
    """已确认字段 {path:raw_text → ResolvedField(term_code, term_name)}。"""

    unresolved_terms: list[ExtractedTerm]
    """需要 recall 的术语列表。"""

    value_enum_map: dict[str, list[str]]
    """whereValue 枚举约束 {path:raw_text → [枚举值列表]}。"""

    provenance: dict[str, str]
    """来源标记 {path:raw_text → 'field_code'|'alias_exact'|'enum_exact'|...}。"""
