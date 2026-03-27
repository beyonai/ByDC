"""类型定义 - 模糊匹配模块。

纯函数式风格，所有类型使用 dataclass(frozen=True) 确保不可变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class FuzzyMatch:
    """模糊匹配结果。

    Attributes:
        term: 匹配到的术语名
        term_id: 术语ID
        term_type: 术语类型
        match_type: 匹配类型 (exact | fuzzy | pinyin)
        similarity: 相似度分数 (0.0 - 1.0)
        edit_distance: 编辑距离
    """

    term: str
    term_id: Optional[str]
    term_type: str
    match_type: str
    similarity: float
    edit_distance: int


@dataclass(frozen=True, slots=True)
class UnmatchedSpan:
    """未匹配文本片段。

    Attributes:
        text: 文本内容
        start: 起始位置
        end: 结束位置
    """

    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class FuzzySuggestion:
    """模糊推荐结果。

    Attributes:
        span: 未匹配片段
        matches: 推荐的匹配列表，按相似度降序排列
    """

    span: UnmatchedSpan
    matches: tuple[FuzzyMatch, ...]


@dataclass(frozen=True, slots=True)
class FuzzyConfig:
    """模糊匹配配置。

    Attributes:
        max_candidates: 最大返回候选数
        score_cutoff: rapidfuzz 最小相似度分数 (0-100)
    """

    max_candidates: int = 5

    # rapidfuzz specific settings
    score_cutoff: float = 50.0  # minimum similarity score (0-100) for rapidfuzz
