"""意图理解原子能力子包。"""

import logging
import os

# 环境变量 DATACLOUD_INTENT_DEBUG=1 开启 intent 全模块 DEBUG 日志
if os.getenv("DATACLOUD_INTENT_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}:
    _intent_logger = logging.getLogger(__name__)
    _intent_logger.setLevel(logging.DEBUG)
    if not _intent_logger.handlers:
        _h = logging.StreamHandler()
        _h.setLevel(logging.DEBUG)
        _h.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        _intent_logger.addHandler(_h)
        _intent_logger.propagate = False  # 避免 root handler 重复输出

from datacloud_knowledge.adapters.opengauss.writer import PostgresTermWriter

from .cache import UserNameCache
from .clarification._expand_query import expand_query
from .clarification.api import analyze_query_clarification
from .disambiguation import build_shortest_path_tree, disambiguate
from .matching import match_mentions, match_mentions_with_search
from .score_update import batch_update_scores, update_score, update_score_async
from .service import (
    batch_update_scores_with_session,
    build_shortest_path_tree_with_session,
    disambiguate_with_session,
    search_all_candidates_with_name_id,
    store_clarification_results,
    typed_multi_recall_with_session,
)
from .types import (
    ClarificationResult,
    DisambiguationResult,
    MatchCandidate,
    MatchResult,
    Mention,
    ScoreUpdateRecord,
    ShortestPathGraphEdge,
    ShortestPathGraphNode,
    ShortestPathTreeNode,
    ShortestPathTreeResult,
    SlotResult,
    SortSemantic,
    StreamEvent,
    StreamEventKind,
    TimeExpr,
)

__all__ = [
    "ClarificationResult",
    "DisambiguationResult",
    "MatchCandidate",
    "MatchResult",
    "Mention",
    "PostgresTermWriter",
    "ScoreUpdateRecord",
    "ShortestPathGraphEdge",
    "ShortestPathGraphNode",
    "ShortestPathTreeNode",
    "ShortestPathTreeResult",
    "SlotResult",
    "SortSemantic",
    "StreamEvent",
    "StreamEventKind",
    "TimeExpr",
    "UserNameCache",
    "analyze_query_clarification",
    "batch_update_scores",
    "batch_update_scores_with_session",
    "build_shortest_path_tree",
    "build_shortest_path_tree_with_session",
    "disambiguate",
    "disambiguate_with_session",
    "expand_query",
    "match_mentions",
    "match_mentions_with_search",
    "search_all_candidates_with_name_id",
    "store_clarification_results",
    "typed_multi_recall_with_session",
    "update_score",
    "update_score_async",
]
