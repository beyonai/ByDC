"""Shared type definitions (Port layer type model).

Protocol signatures forbid bare dict; all return values use frozen dataclasses
defined in this module. mypy provides compile-time protection for new backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObjectSummary:
    """Ontology object summary (list view)."""

    object_code: str
    object_name: str
    description: str = ""
    object_source: str = ""
    field_count: int = 0
    action_count: int = 0
    owner_type: str = "enterprise"
    user_code: str | None = None


@dataclass(frozen=True)
class ViewSummary:
    """View summary."""

    view_code: str
    view_name: str
    description: str = ""
    object_codes: list[str] = field(default_factory=list)
    owner_type: str = "enterprise"
    user_code: str | None = None


@dataclass(frozen=True)
class RelationSummary:
    """Relation summary."""

    relation_code: str
    source_object_code: str
    target_object_code: str
    description: str = ""
    relation_cardinality: str = ""
    owner_type: str = "enterprise"
    user_code: str | None = None


@dataclass(frozen=True)
class ParsedOwlContent:
    """OWL parse result."""

    objects: list[dict[str, Any]] = field(default_factory=list)
    views: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    dbsources: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EmbeddingHit:
    """Vector search hit."""

    term_code: str
    term_type_code: str
    name_text: str
    score: float


@dataclass(frozen=True)
class DimensionProperty:
    """Dimension value -> property resolution result."""

    property_code: str
    object_code: str


@dataclass(frozen=True)
class ReferenceProperty:
    """Referencing side of a property."""

    property_code: str
    property_name: str
    object_code: str
    object_name: str


@dataclass(frozen=True)
class StoredFile:
    """Stored file summary."""

    file_id: str
    key: str
    size_bytes: int
    created_at: str


@dataclass(frozen=True)
class MatchCandidate:
    """Term match candidate.

    Fields match datacloud_knowledge.contracts.types.MatchCandidate.
    Adapters handle mapping.
    """

    term_id: str
    term_name: str
    term_type_code: str
    match_type: str
    confidence: float
    score: float


@dataclass(frozen=True)
class MatchResult:
    """Term match result."""

    exact: dict[str, tuple[MatchCandidate, ...]]
    fuzzy: dict[str, tuple[MatchCandidate, ...]]


@dataclass(frozen=True)
class ScoreUpdateRecord:
    """Score feedback loop update record."""

    name_id: str
    success: bool


@dataclass(frozen=True)
class ObjectInstanceHit:
    """非结构化对象实例检索命中结果。

    每个实例对应一个知识库文件（term_tags.kb_resource_id 唯一绑定）。
    """

    instance_id: str
    """实例 ID（term_id，全局唯一）。"""

    instance_code: str
    """实例编码（term_code，业务编码）。"""

    instance_name: str
    """实例名称（term_name）。"""

    object_code: str
    """对象类型编码（term_type / object_code）。"""

    file_name: str | None
    """对应的知识库文件路径（ext_attrs.kb_file_path）。None 表示无文件关联。"""

    kb_resource_id: str | None
    """知识库资源 ID（ext_attrs.kb_resource_id）。用于下载。None 表示未知。"""

    kb_id: str | None
    """知识库 ID（ext_attrs.kb_id）。用于角色映射和下载路由。None 表示未知。"""

    score: float
    """检索分数（双路 RRF 融合时为 fusion_score，单路时为该路原始分数）。"""


@dataclass(frozen=True)
class ObjectInstanceSearchResult:
    """非结构化对象实例检索批量结果。

    统一返回格式：{keyword: [ObjectInstanceHit, ...]}
    sentence 模式时 dict 只有一个 key（原始 query 文本）。
    word_batch 模式时每个词一个 key。
    """

    results: dict[str, list[ObjectInstanceHit]]


@dataclass(frozen=True)
class ObjectInstanceListItem:
    """对象实例枚举结果项（枚举型接口，非检索命中）。

    与 ObjectInstanceHit 的区别：枚举无分（score 是检索概念），
    取而代之的是图度数 out_degree/in_degree；枚举是确定性集合，
    排序可承诺稳定、total 诚实。

    file_name / kb_resource_id / kb_id 来自 term 的 ext_attrs，
    枚举接口（knowledge 层 T-45）不返回这些字段时恒为 None。
    """

    instance_id: str
    """实例 ID（term_id，全局唯一）。"""

    instance_code: str
    """实例编码（term_code，业务编码）。"""

    instance_name: str
    """实例名称（term_name）。"""

    object_code: str
    """对象类型编码（term_type_code）。"""

    file_name: str | None
    """对应的知识库文件路径（ext_attrs.kb_file_path）。None 表示无/未知。"""

    kb_resource_id: str | None
    """知识库资源 ID（ext_attrs.kb_resource_id）。None 表示未知。"""

    kb_id: str | None
    """知识库 ID（ext_attrs.kb_id，legacy）。None 表示未知。"""

    out_degree: int
    """出度（实例间 BUSINESS 关系计数；无 degree filter 时为 0）。"""

    in_degree: int
    """入度（实例间 BUSINESS 关系计数；无 degree filter 时为 0）。"""


@dataclass(frozen=True)
class ObjectInstanceListPage:
    """对象实例枚举信封（platform 层返回类型）。

    items + 诚实 total（同条件 COUNT）+ 分页回显。RPC handler 据此
    组装 ``{items, total, page, pageSize}`` JSON 信封。
    """

    items: list[ObjectInstanceListItem]
    """当前页条目（9 字段 ObjectInstanceListItem）。"""

    total: int
    """诚实总数（同 WHERE+HAVING 的 COUNT，无 ORDER BY/LIMIT）。"""

    page: int
    """页码（1-based，>=1）。"""

    page_size: int
    """每页条数（>=1）。"""


@dataclass(frozen=True)
class ObjectInstanceDiscoveryHit:
    """非结构化对象实例发现结果项（含已有/新标记与关系信息）。

    instance_id 为 term_id：已有实例为库中原值；新实例为 write action
    响应强校验非空的已创建 term_id。
    """

    instance_id: str
    """实例 ID（term_id，全局唯一）。"""

    instance_code: str
    """实例编码（term_code，业务编码）。"""

    instance_name: str
    """实例名称（term_name）。"""

    object_code: str
    """对象类型编码（term_type_code）。"""

    file_name: str | None
    """对应的知识库文件路径（ext_attrs.kb_file_path）。None 表示无/未知。"""

    kb_resource_id: str | None
    """知识库资源 ID（ext_attrs.kb_resource_id）。None 表示未知。"""

    kb_id: str | None
    """知识库 ID（ext_attrs.kb_id）。None 表示未知。"""

    is_new: bool
    """True=本次新创建，False=库中已有。"""

    evidence: str | None = None
    """原文证据片段；本版恒为 None（TODO）。"""

    relation_name: str = "提及"
    """已建立/将建立的关系名。"""


@dataclass(frozen=True)
class ObjectInstanceDiscoveryResult:
    """发现结果信封（参照 ObjectInstanceSearchResult / ObjectInstanceListPage 模式）。

    已有实例在前、新实例在后。
    """

    items: list[ObjectInstanceDiscoveryHit]


class ObjectInstanceWriteMissingTermIdError(RuntimeError):
    """Write action 响应缺少 term_id 时抛出。

    映射为 500 internal_error（不延迟、不做 pending 标记）。
    """
