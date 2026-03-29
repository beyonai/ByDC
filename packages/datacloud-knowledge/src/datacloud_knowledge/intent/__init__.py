"""意图理解原子能力子包。"""

from .cache import UserNameCache
from .disambiguation import disambiguate
from .matching import match_mentions
from .score_update import batch_update_scores, update_score, update_score_async
from .storage import create_term_knowledge, create_term_with_knowledge, create_user_term_name
from .types import (
    DisambiguationResult,
    MatchCandidate,
    MatchResult,
    Mention,
    ScoreUpdateRecord,
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
    "SlotResult",
    "SortSemantic",
    "TimeExpr",
    # Cache
    "UserNameCache",
    # Score Update (Algorithm E)
    "batch_update_scores",
    # Storage (Algorithm D)
    "create_term_knowledge",
    "create_term_with_knowledge",
    "create_user_term_name",
    # Disambiguation (Algorithm C)
    "disambiguate",
    # Matching (Algorithm B)
    "match_mentions",
    "update_score",
    "update_score_async",
]
