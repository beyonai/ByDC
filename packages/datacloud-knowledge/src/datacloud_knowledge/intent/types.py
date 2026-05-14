"""意图理解类型定义。

纯函数式风格，所有类型使用 dataclass(frozen=True) 确保不可变。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from datacloud_knowledge.contracts.types import (
    MatchCandidate,
    Mention,
)


@dataclass(frozen=True, slots=True)
class SortSemantic:
    """排序意图语义。

    Attributes:
        direction: 排序方向 (ASC|DESC)
        limit: 截断数量，None 表示不限制
        bound_to: 绑定的 mention 文本，None 表示未绑定
    """

    direction: str
    limit: int | None
    bound_to: str | None


@dataclass(frozen=True, slots=True)
class TimeExpr:
    """时间表达结构化结果。

    Attributes:
        start: 时间区间起点，None 表示无下界
        end: 时间区间终点，None 表示无上界
    """

    start: str | None
    end: str | None


@dataclass(frozen=True, slots=True)
class SlotResult:
    """槽位解析结果。

    Attributes:
        mentions: 术语提及列表
        sort_semantics: 排序意图列表
        time_exprs: 时间表达列表
        display_intents: 展示意图列表（可视化类型，不参与查询）
    """

    mentions: tuple[Mention, ...]
    sort_semantics: tuple[SortSemantic, ...] = ()
    time_exprs: tuple[TimeExpr, ...] = ()
    display_intents: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DisambiguationResult:
    """多维消歧结果。

    Attributes:
        confirmed: 确权术语列表，mention_text → candidate
        ambiguous: 歧义术语候选列表，mention_text → candidates
    """

    confirmed: dict[str, MatchCandidate]
    ambiguous: dict[str, tuple[MatchCandidate, ...]]


@dataclass(frozen=True, slots=True)
class ScoreUpdateRecord:
    """Score 闭环更新记录。

    Attributes:
        name_id: 别名记录ID
        success: 本轮对话是否成功（LLM 确认/淘汰）
    """

    name_id: str
    success: bool


@dataclass(frozen=True, slots=True)
class ClarificationResult:
    """查询澄清分析结果。

    Attributes:
        query: 规范化后的查询文本。
        needs_clarification: 是否需要继续向用户澄清。
        form: 需要澄清时返回的结构化表单定义，JSON 字符串。
        knowledge: 无需澄清时返回的结构化知识结果，JSON 字符串。
    """

    query: str
    needs_clarification: bool = False
    form: str = ""
    knowledge: str = ""

    def to_legacy_dict(self) -> dict[str, str | bool]:
        """Return the legacy demo-compatible payload."""
        return {
            "query": self.query,
            "complex_ask_user": self.needs_clarification,
            "form": self.form,
            "knowledge": self.knowledge,
        }


class StreamEventKind(StrEnum):
    """流式事件 kind 的统一枚举定义。"""

    TITLE = "title"
    TOOL_NAME = "tool_name"
    TOOL_ARGS = "tool_args"
    THINKING = "thinking"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    STEP_BEGIN = "step_begin"
    STEP_END = "step_end"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """函数内部流式推送事件。

    用于 analyze_query_clarification 等函数在执行过程中
    向外推送阶段标题、工具调用、思考过程等信息。

    Attributes:
        kind: 事件类型。
        content: 事件内容（文本或 JSON 字符串）。
    """

    kind: StreamEventKind
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", StreamEventKind(self.kind))


@dataclass(frozen=True, slots=True)
class ShortestPathTreeNode:
    """最短路径树节点。"""

    term_id: str
    term_name: str
    term_type_code: str
    description: str | None = None
    relation_from_parent: str = ""
    children: tuple[ShortestPathTreeNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ShortestPathGraphNode:
    """最短路径子图节点。"""

    term_id: str
    term_name: str
    term_type_code: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ShortestPathGraphEdge:
    """最短路径子图边。"""

    source_term_id: str
    target_term_id: str
    relation_name: str


@dataclass(frozen=True, slots=True)
class ShortestPathTreeResult:
    """最短路径子图及树文本结果。"""

    target_term_id: str
    source_term_type_codes: tuple[str, ...]
    root_term_ids: tuple[str, ...]
    nodes: tuple[ShortestPathGraphNode, ...] = ()
    edges: tuple[ShortestPathGraphEdge, ...] = ()
    roots: tuple[ShortestPathTreeNode, ...] = ()
    tree_text: str = ""
