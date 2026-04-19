"""澄清模块数据模型。

定义术语提取、LLM 确认、笛卡尔积展开、paradigmList 构建所需的全部类型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

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


# ── LLM 确认输出 ─────────────────────────────────────────────────────


class ConditionTermMapping(BaseModel):
    """complex_condition 中单个术语的确认结果。"""

    original_term: str = Field(description="原始中文术语，如 '亩产效益'")
    start: int = Field(description="0-based 起始位置")
    end: int = Field(description="exclusive 结束位置")
    confirmed: str | None = Field(
        default=None,
        description="确定 → 填真实字段名；不确定 → None",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="按相关度排序的候选列表",
    )


class ConfirmedCondition(BaseModel):
    """单条 complex_condition 的结构化结果。"""

    original_sentence: str = Field(description="原始 NL 句子，如 '亩产效益后30%的地块'")
    term_mappings: list[ConditionTermMapping] = Field(default_factory=list)


class ClarifyItem(BaseModel):
    """主结构中需要用户澄清的项。"""

    keyword: str = Field(description="原始中文术语")
    candidates: list[str] = Field(description="候选列表")
    reason: str = Field(default="", description="澄清原因")
    source: str = Field(default="", description="来源槽位: select / where / group_by / order_by")
    path: str = Field(default="", description="JSON pointer，供 format 精确替换")


class ConfirmedStructuredQuery(BaseModel):
    """提交查询确认结果。将中文术语映射到真实 schema 字段后，调用此工具提交确认结果。确定的术语直接替换，无法确定的放入 clarify_items。"""

    select: list[str] = Field(
        default_factory=list,
        description="确认后的查询字段列表，用召回候选中的真实字段名替换原始中文术语",
    )
    filters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的过滤条件，field 用真实字段名替换",
    )
    order_by: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的排序条件",
    )
    limit: int | None = None
    offset: int | None = None
    filter_relation: str = "AND"

    confirmed_conditions: list[ConfirmedCondition] = Field(
        default_factory=list,
        description="complex_conditions 中每条 NL 的术语确认结果",
    )
    clarify_items: list[ClarifyItem] = Field(
        default_factory=list,
        description="无法确定的术语，需要用户从候选中选择",
    )
    needs_clarification: bool = Field(
        default=False,
        description="true 表示存在无法确定的术语，需要用户澄清",
    )


class ConfirmedStructuredCompute(BaseModel):
    """提交统计分析确认结果。将中文术语映射到真实 schema 字段后，调用此工具提交确认结果。确定的术语直接替换，无法确定的放入 clarify_items。"""

    dimensions: list[str | dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的分组维度，用真实字段名替换原始中文术语",
    )
    metrics: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的指标列表，field 用真实字段名替换",
    )
    filters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的过滤条件，field 用真实字段名替换",
    )
    having: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的 having 条件",
    )
    order_by: list[dict[str, Any]] = Field(
        default_factory=list,
        description="确认后的排序条件",
    )
    limit: int | None = None
    filter_relation: str = "AND"

    confirmed_conditions: list[ConfirmedCondition] = Field(
        default_factory=list,
        description="complex_conditions 中每条 NL 的术语确认结果",
    )
    clarify_items: list[ClarifyItem] = Field(
        default_factory=list,
        description="无法确定的术语，需要用户从候选中选择",
    )
    needs_clarification: bool = Field(
        default=False,
        description="true 表示存在无法确定的术语，需要用户澄清",
    )


# ── 内部元数据（存入 ClarificationResult.knowledge） ─────────────────


class KnowledgeMeta(BaseModel):
    """paradigmList 构建时的内部元数据，供 format 阶段精确替换。

    存入 ClarificationResult.knowledge 的 JSON 中。
    """

    path_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="paradigm item kid → ExtractedTerm.path 映射",
    )
    confirmed_conditions: list[ConfirmedCondition] = Field(
        default_factory=list,
        description="complex_conditions 的 LLM 确认结果",
    )
    mode: Literal["query", "compute"] = Field(description="输入模式")
