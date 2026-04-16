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

from .cache import UserNameCache
from .clarification import analyze_query_clarification
from .disambiguation import build_shortest_path_tree, disambiguate
from .matching import match_mentions, match_mentions_with_search
from .natquery import NatQuery, SelectExpr, WhereClause, expand_query, natquery_to_five_stage
from .paradigm_builder import (
    AGGREGATIONS_KEY,
    FILTERS_KEY,
    GROUP_BY_KEY,
    ORDER_BY_KEY,
    QUERY_TARGETS_KEY,
    ParadigmResolutionState,
    RecallCandidate,
    TypedKeywordState,
    build_paradigm_resolution_state,
    five_stage_keys_from_raw,
)
from .score_update import batch_update_scores, update_score, update_score_async
from .service import (
    batch_update_scores_with_session,
    build_shortest_path_tree_with_session,
    disambiguate_with_session,
    search_all_candidates_with_name_id,
    store_clarification_results,
    typed_multi_recall_with_session,
)
from .storage import create_term_knowledge, create_term_with_knowledge, create_user_term_name
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
    # NatQuery (NL → 结构化查询展开)
    "NatQuery",
    "SelectExpr",
    "WhereClause",
    "expand_query",
    "natquery_to_five_stage",
    # Paradigm builder (五段式 → 召回 → paradigmList)
    "AGGREGATIONS_KEY",
    "FILTERS_KEY",
    "GROUP_BY_KEY",
    "ORDER_BY_KEY",
    "QUERY_TARGETS_KEY",
    "ParadigmResolutionState",
    "RecallCandidate",
    "TypedKeywordState",
    "build_paradigm_resolution_state",
    "five_stage_keys_from_raw",
    # Types
    "ClarificationResult",
    "DisambiguationResult",
    "MatchCandidate",
    "MatchResult",
    "Mention",
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
    # Cache
    "UserNameCache",
    "analyze_query_clarification",
    "batch_update_scores",
    "batch_update_scores_with_session",
    "build_shortest_path_tree",
    "build_shortest_path_tree_with_session",
    "create_term_knowledge",
    "create_term_with_knowledge",
    "create_user_term_name",
    "disambiguate",
    "disambiguate_with_session",
    "match_mentions",
    "match_mentions_with_search",
    "search_all_candidates_with_name_id",
    "store_clarification_results",
    "typed_multi_recall_with_session",
    "update_score",
    "update_score_async",
]
