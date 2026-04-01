"""意图理解原子能力子包。"""

from .cache import UserNameCache
from .disambiguation import build_shortest_path_tree, disambiguate
from .matching import match_mentions, match_mentions_with_search
from .score_update import batch_update_scores, update_score, update_score_async
from .service import (
    batch_update_scores_with_session,
    build_shortest_path_tree_with_session,
    disambiguate_with_session,
    search_all_candidates_with_name_id,
    store_clarification_results,
)
from .storage import create_term_knowledge, create_term_with_knowledge, create_user_term_name
from .types import (
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
    TimeExpr,
)

__all__ = [
    # Types
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
    "TimeExpr",
    # Cache
    "UserNameCache",
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
    "match_mentions",
    "match_mentions_with_search",
    "search_all_candidates_with_name_id",
    "store_clarification_results",
    "update_score",
    "update_score_async",
]
