from __future__ import annotations

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
