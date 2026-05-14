"""澄清模块数据模型。

定义 LLM 确认、笛卡尔积展开、paradigmList 构建所需的全部类型。

共享类型 ExtractedTerm、PreResolveResult 已提取至 contracts/intent_types.py，
本模块从那里重导出以保持向后兼容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

# 共享类型 — 从 contracts 层重导出，供 clarification 内部及 retrieval/ 共同使用
from datacloud_knowledge.contracts.intent_types import (  # noqa: F401
    ExtractedTerm,
    PreResolveResult,
)

if TYPE_CHECKING:
    from datacloud_knowledge.contracts.types import ResolvedField


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


# ── 分治确认 LLM 输出 schema ─────────────────────────────────────────


class TermConfirmation(BaseModel):
    """主结构中单个编号术语的确认结果。"""

    term_id: int = Field(description="输入中的 #编号")
    confirmed: str | None = Field(
        default=None,
        description="确认值；无法确定时为 null",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="confirmed=null 时，按相关度降序的候选列表",
    )
    reason: str = Field(default="", description="澄清原因")


class MainConfirmResult(BaseModel):
    """主结构术语确认结果。对每个待确认术语选择最匹配的候选或标记需澄清。"""

    confirmations: list[TermConfirmation] = Field(
        description="每个编号术语的确认结果",
    )
    needs_clarification: bool = Field(
        default=False,
        description="true 表示存在无法确定的术语",
    )


class CCTermConfirmation(BaseModel):
    """complex_condition 中单个编号术语的确认结果。"""

    term_id: int = Field(description="输入中的 #编号")
    confirmed: str | None = Field(
        default=None,
        description="确认值；无法确定时为 null",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="confirmed=null 时，按相关度降序的候选列表",
    )
    reason: str = Field(default="", description="澄清原因")


class CCConfirmResult(BaseModel):
    """单条 complex_condition 确认结果。"""

    confirmations: list[CCTermConfirmation] = Field(
        description="每个编号术语的确认结果",
    )
    needs_clarification: bool = Field(
        default=False,
        description="true 表示存在无法确定的术语",
    )


# ── 分治确认内部元数据 ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TermMeta:
    """主结构编号术语的内部元数据。"""

    path: str
    """JSON pointer，如 'select.0' / 'filters.1.value.0'。"""

    ktype: str
    """召回类型：select / whereKey / whereValue / orderBy / groupBy。"""

    raw_text: str
    """原始术语文本。"""


@dataclass(frozen=True, slots=True)
class CCTermMeta:
    """CC 编号术语的内部元数据。"""

    raw_text: str
    """原始术语文本。"""

    ktype: str
    """召回类型。"""

    start: int
    """0-based 起始位置（来自抽取器）。"""

    end: int
    """exclusive 结束位置（来自抽取器）。"""

    condition_index: int
    """所属 complex_condition 索引。"""
