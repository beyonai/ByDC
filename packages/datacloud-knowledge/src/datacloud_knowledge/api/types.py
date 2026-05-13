"""共享类型定义 — 术语检索、别名消歧、搜索召回、写入操作。

此模块迁移并精炼自 knowledge_search/types.py，新增搜索召回结果类型和写入操作类型。
所有类型均使用 frozen dataclass 或 Pydantic BaseModel，无外部副作用依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ═══════════════════════════════════════════════════════════════════════════════
# 原子类型
# ═══════════════════════════════════════════════════════════════════════════════

ClarificationMode = Literal["query", "compute"]
"""澄清模式：query=查询模式，compute=计算模式。"""

TagOp = Literal["eq", "like", "gt", "gte", "lt", "lte", "in"]
"""标签过滤操作符。"""

TagValueType = Literal["text", "number", "timestamp"]
"""标签值类型。"""

OpaquePayload = dict[str, Any] | list[Any] | str
"""不透明载荷：序列化后的澄清表单、元数据等任意结构化数据。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 标签过滤
# ═══════════════════════════════════════════════════════════════════════════════


class TagFilter(BaseModel):
    """术语标签过滤条件。

    Attributes:
        key: 标签键名。
        op: 过滤操作符（eq/like/gt/gte/lt/lte/in）。
        value_type: 标签值类型（text/number/timestamp），默认为 text。
        value: 过滤值，op=in 时为字符串列表，否则为单值字符串。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    op: TagOp
    value_type: TagValueType = "text"
    value: str | list[str]


# ═══════════════════════════════════════════════════════════════════════════════
# 术语查询结果
# ═══════════════════════════════════════════════════════════════════════════════


class TermBrief(BaseModel):
    """术语简要信息。"""

    model_config = ConfigDict(extra="forbid")

    term_id: str
    term_name: str
    owl_doc_id: str


class TermItem(BaseModel):
    """术语详情条目（搜索返回的单个术语）。

    Attributes:
        term_id: 术语 ID。
        term_code: 术语编码。
        term_name: 术语标准名称。
        term_type_code: 术语类型编码。
        desc_summary: 描述摘要（前 100 字）。
        term_tags: 术语标签属性（JSONB）。
        owl_doc_id: OWL 本体定义文件 ID。
        created_time: 创建时间。
        updated_time: 更新时间。
        score: 搜索相关性分数（可选）。
    """

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
    """术语搜索分页结果。

    Attributes:
        total: 总命中数。
        items: 当前页术语条目列表。
    """

    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[TermItem]


class OwlResolveRoot(BaseModel):
    """OWL 消歧根节点（关联术语根）。"""

    model_config = ConfigDict(extra="forbid")

    term_type_code: str
    term_codes: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 名称、属性、值
# ═══════════════════════════════════════════════════════════════════════════════


class NameItem(BaseModel):
    """术语名称项。

    Attributes:
        name_text: 名称文本。
        is_primary: 是否为标准名称（True）或别名（False）。
    """

    model_config = ConfigDict(extra="forbid")

    name_text: str
    is_primary: bool


class PropItem(BaseModel):
    """对象/视图下的属性术语。

    Attributes:
        term_id: 属性术语 ID。
        term_code: 属性术语编码。
        term_name: 属性术语标准名称。
    """

    model_config = ConfigDict(extra="forbid")

    term_id: str
    term_code: str
    term_name: str


class ValueWithAliases(BaseModel):
    """属性值术语及其别名。

    Attributes:
        parent_term_id: 父级属性术语 ID。
        term_id: 值术语 ID。
        term_code: 值术语编码。
        term_name: 值术语标准名称。
        aliases: 值术语的所有别名。
    """

    model_config = ConfigDict(extra="forbid")

    parent_term_id: str
    term_id: str
    term_code: str
    term_name: str
    aliases: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 字段别名消歧类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class AmbiguousCandidate:
    """一个歧义候选：同一输入别名匹配到多个不同 prop 时的单条候选。

    Attributes:
        term_code: 候选字段编码。
        term_name: 候选字段标准名称。
        matched_alias: 触发匹配的原始别名。
        scope: 作用域信息（view/object/global + code）。
    """

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


# ═══════════════════════════════════════════════════════════════════════════════
# 扩展字段解析类型（含 term_name）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ResolvedField:
    """精确命中的字段解析结果（含中文标准名）。

    Attributes:
        term_code: 字段编码（prop 的 term_code）。
        term_name: 字段中文标准名（prop 的 term_name）。
    """

    term_code: str
    term_name: str


@dataclass(frozen=True, slots=True)
class FieldResolutionResultWithNames:
    """扩展版字段别名消歧结果（resolved 含 term_name）。

    Attributes:
        resolved: 无歧义命中 {输入别名 → ResolvedField}。
        ambiguous: 多候选歧义 {输入别名 → 候选列表}。
        unresolved: 完全未命中的输入别名。
    """

    resolved: dict[str, ResolvedField] = field(default_factory=dict)
    ambiguous: dict[str, list[AmbiguousCandidate]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 搜索召回结果类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class BM25Result:
    """BM25 全文搜索召回结果。

    Attributes:
        term_id: 术语 ID。
        term_name: 术语名称。
        name_id: 术语名称记录 ID。
        term_type_code: 术语类型编码。
        score: BM25 相关性分数（ts_rank_cd 输出）。
        term_code: 术语编码。
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    score: float
    term_code: str = ""


@dataclass(frozen=True, slots=True)
class SubstringResult:
    """子串匹配召回结果。

    Attributes:
        term_id: 术语 ID。
        term_name: 术语名称。
        name_id: 术语名称记录 ID。
        term_type_code: 术语类型编码。
        score: 匹配长度分数（术语名称字符数）。
        term_code: 术语编码。
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    score: float
    term_code: str = ""


@dataclass(frozen=True, slots=True)
class VectorResult:
    """向量语义搜索召回结果。

    Attributes:
        term_id: 术语 ID。
        term_name: 术语名称。
        name_id: 术语名称记录 ID。
        term_type_code: 术语类型编码。
        similarity: 余弦相似度（0-1，1 为完全相似）。
        term_code: 术语编码。
    """

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    similarity: float
    term_code: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# 写入操作类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class TermNameCreate:
    """批量创建术语名称的请求项。

    Attributes:
        name_text: 别名文本。
        term_id: 归属术语 ID。
        user_id: 创建用户 ID（可选）。
        search_scope: 搜索作用域定义（JSONB 格式字典）。
    """

    name_text: str
    term_id: str
    user_id: str | None = None
    search_scope: dict[str, object] = field(default_factory=dict)
