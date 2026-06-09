"""共享类型定义 — capabilities/ 模块的协议参数类型。

从 contracts/types.py 中提取的通用共享类型，供 TermStore 和 TermStoreExtended
协议使用。零外部依赖，纯 Python dataclass。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class TermCreate:
    """单条术语新增请求。

    映射到 ``POST /file/importMultipleTerm`` 请求体。
    外部 API 无 ``desc`` 字段，desc 通过 ``ext_attrs["desc"]`` 或
    ``labels["_desc"]`` 透传。``labels`` 的 key 是系统注册的 label 类型编码
    （如 ``"staffName"``），value 是标签编码值。
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


# ═══════════════════════════════════════════════════════════════════════════════
# 输出类型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class TermItem:
    """搜索返回的术语摘要。

    对应 ``POST /core/term/queryStandardTerm`` 响应中
    ``resultObject.termInfoList[]``。外部 API 中 ``label`` 和 ``ext_attrs``
    是 JSON 字符串，adapter 层负责解析为 dict。``score`` 字段仅 OpenGauss
    adapter（BM25 / 向量）时有值，HTTP adapter 返回 None。
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
    """术语库 ID。"""
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

    对应 ``POST /core/term/queryTermDetail`` 或
    ``POST /core/terms/pageList`` 响应。``term_type_name`` 是术语类型的
    翻译名称（如 "员工姓名"），区别于 ``term_type`` 的类型编码（如 "userName"）。
    """

    parent_term_name: str = ""
    """父术语标准名称。"""
    label_info: list[dict[str, str]] = field(default_factory=list)
    """翻译后的标签信息列表。"""
    synonym_list: list[str] = field(default_factory=list)
    """同义词列表（已 split）。"""
    term_type_name: str = ""
    """术语类型翻译名称。"""


@dataclass(frozen=True, slots=True)
class QueryResult:
    """分页检索结果。"""

    total: int
    """总命中数。"""
    items: list[TermItem]
    """当前页术语条目列表（list_terms 场景下实际为 TermDetail 实例）。"""


@dataclass(frozen=True, slots=True)
class ImportResult:
    """批量新增结果。"""

    created: int
    """成功创建数。"""
    term_ids: list[str]
    """新创建的 term_id 列表。"""
    errors: list[str] = field(default_factory=list)
    """错误信息列表。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 最短路径树类型（供 TermStoreExtended 使用）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ShortestPathNode:
    """最短路径树查询的单行结果，封装递归 CTE 返回的路径节点信息。

    Attributes:
        term_id: 满足根类型约束的候选根术语 ID。
        term_name: 术语标准名。
        term_type_code: 术语类型编码。
        description: 术语描述（取自 desc_summary 或 term_knowledge 首条）。
        depth: 从目标术语到根节点的图距离（跳数）。
        path_term_ids: 路径上所有术语 ID 列表（根→目标，目标在尾部）。
        path_term_names: 路径上所有术语名称列表。
        path_term_type_codes: 路径上所有术语类型编码列表。
        path_term_desc_summaries: 路径上所有术语描述摘要列表。
        path_descriptions: 路径上所有术语的 knowledge 描述列表。
        path_relations: 路径上所有关系名称列表（目标→根方向）。
    """

    term_id: str
    term_name: str
    term_type_code: str
    description: str | None
    depth: int
    path_term_ids: list[str]
    path_term_names: list[str]
    path_term_type_codes: list[str]
    path_term_desc_summaries: list[str]
    path_descriptions: list[str]
    path_relations: list[str]


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ImportResult",
    "LabelCondition",
    "LabelFilter",
    "QueryResult",
    "QueryType",
    "ShortestPathNode",
    "TermCreate",
    "TermDetail",
    "TermItem",
    "TermUpdate",
]
