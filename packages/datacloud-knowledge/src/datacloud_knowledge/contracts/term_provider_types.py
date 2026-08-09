"""TermProvider 协议专用类型 — 纯 dataclass，零外部依赖。

定义术语 CRUD 操作的输入/输出类型，包括检索、列表、详情、导入、更新。
独立于 protocols.py，安全被任何模块导入（领域模型独立原则）。

参考: _Architecture Patterns with Python_ 第 1 章「领域模型独立」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

# ═══════════════════════════════════════════════════════════════════════════════
# 字面量类型
# ═══════════════════════════════════════════════════════════════════════════════

QueryType = Literal["fulltext", "exact", "embedding", "mixed"]
"""检索策略:
- fulltext: 全文检索（BM25 / 子串）
- exact:    精确匹配 term_name / term_code
- embedding: 语义向量检索
- mixed:    混合召回（全文 + 向量，RRF 融合）
"""

LabelCondition = Literal["and", "or"]
"""标签过滤组合条件。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举型查询类型（enumerate_object_instances）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ObjectInstanceItem:
    """对象实例枚举结果项（term 行 + 图度数）。

    ``out_degree``/``in_degree`` 仅在请求包含 degree filter（触发 JOIN）时
    为真实**范围度数**（对端在 object_codes ∪ kb_resource_ids 并集内才计数，
    ）；无 degree filter 时不做 JOIN，恒为 0。
    """

    term_id: str
    term_code: str
    term_name: str
    term_type_code: str
    out_degree: int = 0
    in_degree: int = 0


@dataclass(frozen=True, slots=True)
class EnumeratedObjectInstances:
    """对象实例枚举信封 — items + 诚实 total（同条件 COUNT 变体）。"""

    items: list[ObjectInstanceItem]
    total: int


@dataclass(frozen=True, slots=True)
class SortSpec:
    """枚举查询排序规格 — sort 数组单元素请求形状。

    与 FilterSpec 请求元素同构：单一 key（by）+ params 参数字典。
    ``by`` 目前仅支持 ``"similarity"``（语义相似度排序，EmbeddingService
    形态落地）；新排序依据 = 扩展 Literal + _SORT_REGISTRY 条目，
    本层仅定形状，不做任何排序逻辑。
    """

    by: Literal["similarity"]
    """排序依据。目前仅 "similarity"。"""
    params: dict[str, Any] = field(default_factory=dict)
    """类型专属参数字典（如 embedding 查询所需参数）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 输入类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class LabelFilter:
    """单个标签过滤条件。

    三种模式：
    - 等值过滤:         filter_value 不为 None
    - 范围过滤:         min_filter_value / max_filter_value 不为 None
    - 等值 + 范围共存:  同时满足
    """

    field_code: str
    """标签字段编码（labelTypeCode）。"""
    filter_value: str | None = None
    """等值过滤值。"""
    min_filter_value: int | float | None = None
    """范围过滤最小值。"""
    max_filter_value: int | float | None = None
    """范围过滤最大值。"""


class FilterSpec(TypedDict, total=True):
    """``query_terms_by_labels`` 通用过滤通道元素（结构契约）。

    三键均必填（TypedDict ``total=True`` 语义）：缺任一键 → 契约错误
    （调用方入口抛 ``ValueError``，不宽容跳过）。与 label_filters 的
    「数据内容无效可跳过」定位不同——filters 是结构契约通道。

    - ``field`` 必须 ∈ 白名单（knowledge 层 ``_FILTER_FIELD_MAP``：
      ``kb_id`` / ``kb_resource_id`` / ``kb_file_path`` / ``term_type_code``），
      不在白名单 → 契约错误；
    - ``op`` 仅支持 ``"eq"``（单值等值，恰 1 值）/ ``"in"``（列表匹配，≥0 值）；
    - ``values`` 空列表按 op 分派：``in`` + ``[]`` = 全滤 ``return []``；
      ``eq`` + ``[]`` = 契约错误（eq 需恰 1 值）。
    """

    field: str
    """过滤维度（白名单 field 名）。"""
    op: Literal["eq", "in"]
    """比较操作。eq = 精确等值（恰 1 个值）；in = 列表匹配（≥0 个值）。"""
    values: list[str]
    """匹配值列表。元素绑定前统一 ``str(v)`` 转换。"""


@dataclass(frozen=True, slots=True)
class TermCreate:
    """单条术语新增请求。

    映射到 ``POST /file/importMultipleTerm`` 请求体。
    外部 API 无 ``desc`` 字段，desc 通过 ``ext_attrs["desc"]`` 或 ``labels["_desc"]`` 透传。
    ``labels`` 的 key 是系统注册的 label 类型编码（如 ``"staffName"``），
    value 是标签编码值。
    """

    term_name: str
    """术语标准名称。"""
    term_code: str
    """术语编码（业务唯一标识）。"""
    term_type: str
    """术语类型编码。传 "-1" 表示创建术语类型本身。"""
    parent_term_code: str = ""
    """父术语编码。"""
    desc: str = ""
    """术语描述。写入时映射到 ext_attrs["desc"]；读取时从 termDesc 取。"""
    labels: dict[str, str] = field(default_factory=dict)
    """标签映射 {labelTypeCode: labelCode}。"""
    ext_attrs: dict[str, str] = field(default_factory=dict)
    """百应拓展字段。"""
    synonyms: list[str] = field(default_factory=list)
    """同义词列表 → synonymList。"""
    relations: list[dict[str, str]] = field(default_factory=list)
    """关系列表。每条含 term_name / term_code / relation_name / relation_category / cardinality。"""


@dataclass(frozen=True, slots=True)
class TermUpdate:
    """单条术语更新请求。仅非空字段会被更新。

    映射到 ``POST /core/terms/updateTerm`` 请求体。
    外部 API 通过 ``termId`` 定位术语，不需要 ``termCode`` 在协议参数中。
    """

    term_name: str | None = None
    """术语标准名称。"""
    term_code: str | None = None
    """术语编码（外部 API 要求传 termCode 用于定位）。"""
    term_type: str | None = None
    """术语类型编码。"""
    parent_term_code: str | None = None
    """父术语编码。"""
    desc: str | None = None
    """术语描述。写入时映射到 ext_attrs["desc"]。"""
    labels: dict[str, str] | None = None
    """标签映射 {labelTypeCode: labelCode}。"""
    ext_attrs: dict[str, str] | None = None
    """百应拓展字段。"""
    synonyms: list[str] | None = None
    """同义词列表 → synonymList。"""
    domain_ids: list[str] | None = None
    """所属领域 ID 列表。用于场景归属时补写。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 输出类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class TermItem:
    """搜索返回的术语摘要。

    对应 ``POST /core/term/queryStandardTerm`` 响应中 ``resultObject.termInfoList[]``。
    外部 API 中 ``label`` 和 ``ext_attrs`` 是 JSON 字符串，adapter 层负责解析为 dict。
    ``score`` 字段仅 OpenGauss adapter（BM25 / 向量）时有值，HTTP adapter 返回 None。
    """

    term_id: str
    """术语 ID。"""
    term_code: str
    """术语编码。"""
    term_name: str
    """术语标准名称。"""
    term_type: str
    """术语类型编码。"""
    dataset_id: str
    """术语库 ID。**已弃用** — 请使用 ``library_id``（ADR-002）。"""
    library_id: str = ""
    """术语库 ID（新名称，ADR-002）。当未显式设置时，从 ``dataset_id`` 回退。"""
    parent_term_code: str = ""
    """父术语编码。"""
    desc: str = ""
    """术语描述 → termDesc。"""
    labels: dict[str, str] = field(default_factory=dict)
    """标签映射（外部 API 是 JSON 字符串，adapter 层解析为 dict）。"""
    synonyms: str = ""
    """"|" 分隔的同义词字符串。"""
    ext_attrs: dict[str, str] = field(default_factory=dict)
    """拓展属性 → extAttribution（JSON 字符串，adapter 层解析为 dict）。"""
    created_time: int = 0
    """创建时间（epoch millis）。"""
    updated_time: int = 0
    """更新时间（epoch millis）。"""
    score: float | None = None
    """相关性分数。仅 OpenGauss adapter；HTTP adapter 恒为 None。"""
    # 以下字段仅外部 API 返回，OpenGauss adapter 为空字符串：
    dataset_data_id: str = ""
    """数据集数据 ID（仅外部 API）。"""
    dataset_file_id: str = ""
    """数据集文件 ID（仅外部 API）。"""
    external_id: str = ""
    """外部系统 ID（仅外部 API）。"""
    unique_code: str = ""
    """唯一编码（仅外部 API）。"""


@dataclass(frozen=True, slots=True)
class TermDetail(TermItem):
    """单条术语完整详情（含翻译后的 labelInfo 和父术语名称）。

    对应 ``POST /core/term/queryTermDetail`` 或 ``POST /core/terms/pageList`` 响应。
    ``term_type_name`` 是术语类型的翻译名称（如 "员工姓名"），
    区别于 ``term_type`` 的类型编码（如 "userName"）。

    .. versionchanged:: 0.3.0
        新增 domain, parent_chain, names, knowledges, children_count,
        relation_count, term_tags 字段（term API 重构）。
    """

    parent_term_name: str = ""
    """父术语标准名称。"""
    label_info: list[dict[str, str]] = field(default_factory=list)
    """翻译后的标签信息列表。"""
    synonym_list: list[str] = field(default_factory=list)
    """同义词列表（已 split）。"""
    term_type_name: str = ""
    """术语类型翻译名称。"""

    # ── term API 重构新增字段 ─────────────────────────────────────

    domain: list[dict[str, str]] = field(default_factory=list)
    """所属领域列表 [{code, name}, ...]（term_domain 表翻译）。"""
    parent_chain: list[dict[str, str]] = field(default_factory=list)
    """父术语链 [{termId, termCode, termName}, ...]，从直接父级到根。"""
    names: list[dict[str, Any]] = field(default_factory=list)
    """术语别名列表 [{name_id, name_text, search_scope}, ...]（term_name 表）。"""
    knowledges: list[dict[str, Any]] = field(default_factory=list)
    """关联知识列表（term_knowledge 表）。"""
    children_count: int = 0
    """直接子术语数。"""
    relation_count: int = 0
    """关联关系总数（作为 source 或 target）。"""
    term_tags: dict[str, Any] = field(default_factory=dict)
    """术语标签属性（JSONB 原文）。"""


@dataclass(frozen=True, slots=True)
class QueryResult:
    """分页检索结果。"""

    total: int
    """总命中数。"""
    items: list[TermItem]
    """当前页术语条目列表（list_terms 场景下实际为 TermDetail 实例）。"""


@dataclass(frozen=True, slots=True)
class ImportResult:
    """批量导入结果。"""

    created: int
    """成功创建数。"""
    updated: int = 0
    """更新数（已有术语被覆盖）。"""
    skipped: int = 0
    """跳过数（空名称或异常跳过）。"""
    term_ids: list[str] = field(default_factory=list)
    """创建或更新的 term_id 列表。"""
    errors: list[str] = field(default_factory=list)
    """错误信息列表。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "FilterSpec",
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
