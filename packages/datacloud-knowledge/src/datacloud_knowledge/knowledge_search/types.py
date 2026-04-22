from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TagOp = Literal["eq", "like", "gt", "gte", "lt", "lte", "in"]
TagValueType = Literal["text", "number", "timestamp"]


class TagFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    op: TagOp
    value_type: TagValueType = "text"
    value: str | list[str]


class TermBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: str
    term_name: str
    owl_doc_id: str


class TermItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: str
    term_code: str
    term_name: str
    term_type_code: str
    desc_summary: str | None = None
    term_tags: dict[str, Any] = Field(default_factory=dict)
    owl_doc_id: str | None = None
    created_time: Any | None = None
    updated_time: Any | None = None
    score: float | None = None


class SearchTermsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[TermItem]


class OwlResolveRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_type_code: str
    term_codes: list[str] = Field(default_factory=list)


class NameItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_text: str
    is_primary: bool


class PropItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: str
    term_code: str
    term_name: str


class ValueWithAliases(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_term_id: str
    term_id: str
    term_code: str
    term_name: str
    aliases: list[str] = Field(default_factory=list)


# ── 字段别名消歧类型 ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AmbiguousCandidate:
    """一个歧义候选：同一输入别名匹配到多个不同 prop 时的单条候选。"""

    term_code: str
    term_name: str
    matched_alias: str
    scope: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FieldResolutionResult:
    """字段别名精确消歧结果。

    Attributes:
        resolved: 无歧义命中 {输入别名 → field_code}。
        ambiguous: 多候选歧义 {输入别名 → 候选列表}。
        unresolved: 完全未命中的输入别名。
    """

    resolved: dict[str, str] = field(default_factory=dict)
    ambiguous: dict[str, list[AmbiguousCandidate]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ValueResolutionResult:
    """属性值术语精确消歧结果。

    Attributes:
        matched: 命中的输入值集合（值在 scope 下的 prop child term 中存在）。
        unmatched: 未命中的输入值列表。
    """

    matched: set[str] = field(default_factory=set)
    unmatched: list[str] = field(default_factory=list)
