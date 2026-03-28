"""模糊匹配模块。

基于 rapidfuzz 实现高效模糊匹配：
- 初始化时间：0ms（无需构建索引）
- 查询时间：30-40ms（26K词汇）
- 内存占用：小（只保存词汇列表）

Usage:
    from datacloud_knowledge.query.fuzzy import (
        FuzzyMatch,
        FuzzySuggestion,
        UnmatchedSpan,
        FuzzyConfig,
        create_matcher,
        match_all_unmatched,
    )

    # 创建匹配器（rapidfuzz 不需要预构建索引）
    term_metadata, config, stopwords = create_matcher(term_metadata)

    # 匹配未匹配片段
    suggestions = match_all_unmatched(spans, term_metadata, config, stopwords)
"""

from .matcher import (
    DEFAULT_STOPWORDS,
    create_matcher,
    match_all_unmatched,
)
from .types import (
    FuzzyConfig,
    FuzzyMatch,
    FuzzySuggestion,
    UnmatchedSpan,
)

__all__ = [
    # Types
    "FuzzyMatch",
    "FuzzySuggestion",
    "UnmatchedSpan",
    "FuzzyConfig",
    # Main API functions
    "create_matcher",
    "match_all_unmatched",
    "DEFAULT_STOPWORDS",
]
