"""术语匹配 — 已下沉到 retrieval.mention_matching，此文件保留向后兼容重导出。"""

from __future__ import annotations

# 重导出以保证向后兼容
from datacloud_knowledge.retrieval.mention_matching import (
    DEFAULT_FUZZY_MAX_CANDIDATES,
    DEFAULT_FUZZY_SCORE_CUTOFF,
    SearchMode,
    match_mentions,
    match_mentions_with_search,
)

__all__ = [
    "DEFAULT_FUZZY_MAX_CANDIDATES",
    "DEFAULT_FUZZY_SCORE_CUTOFF",
    "SearchMode",
    "match_mentions",
    "match_mentions_with_search",
]
