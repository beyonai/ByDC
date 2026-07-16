"""Term network graph data structures for knowledge graph traversal.

Resolved terms, edges, paths, and gaps model the graph entities used during
term-to-term traversal and path resolution in the knowledge graph layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResolvedTerm:
    """A term resolved to a specific knowledge base entry."""

    term_id: str
    term_name: str
    term_type: str
    kb_id: str
    kb_file_path: str
    matched_by: str  # always "exact"


@dataclass(frozen=True, slots=True)
class Edge:
    """Directed edge between two terms in the knowledge graph."""

    source: str
    target: str
    relation: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str
    source_attrs: dict[str, Any]
    target_attrs: dict[str, Any]

    def other_end(self, node_id: str) -> str:
        """Return the node at the opposite end of this edge."""
        return self.target if node_id == self.source else self.source

    def reversed(self) -> Edge:
        """Return a new Edge with source and target swapped."""
        return Edge(
            source=self.target,
            target=self.source,
            relation=self.relation,
            source_name=self.target_name,
            target_name=self.source_name,
            source_type=self.target_type,
            target_type=self.source_type,
            source_attrs=self.target_attrs,
            target_attrs=self.source_attrs,
        )


@dataclass(frozen=True, slots=True)
class ScoredEdge:
    """A graph edge augmented with a relevance score and traversal depth."""

    edge: Edge
    score: float
    hops_from_seed: int


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A knowledge-graph term entry used in catalogue listings.

    Attributes:
        term_id: Unique identifier of the term node.
        term_name: Human-readable name of the term.
        term_type: Type/category of the term.
        kb_file_path: Path to the knowledge-base file this term belongs to.
        unshown_edge_count: Number of edges hidden from the catalogue view.
        unshown_relations: Relation names of hidden edges.
        unshown_neighbors: Neighbour term names reachable via hidden edges.
    """

    term_id: str
    term_name: str
    term_type: str
    kb_file_path: str
    unshown_edge_count: int
    unshown_relations: list[str]
    unshown_neighbors: list[str]


@dataclass(frozen=True, slots=True)
class SuggestedSeed:
    """A routing suggestion: term to add as a seed for deeper exploration."""

    term_id: str
    term_name: str
    reason: str
    hops_from_seed: int


@dataclass(frozen=True, slots=True)
class Gap:
    """A term that could not be resolved during graph traversal."""

    term: str
    reason: str  # "no_exact_match"
    resolution: str  # "unresolved" | "mapped_to"
    resolved_term_name: str = ""


@dataclass(frozen=True, slots=True)
class SubgraphStats:
    """Aggregated statistics for a knowledge-graph subgraph.

    Attributes:
        relation_freq: Frequency count of each relation name in the subgraph.
        node_degree: Degree (edge count) of each node in the subgraph.
    """

    relation_freq: dict[str, int]
    node_degree: dict[str, int]


def _relation_quality(relation_name: str, stats: SubgraphStats) -> float:
    """Compute a quality score [0.3, 3.0] for a relation based on subgraph statistics.

    The score combines a baseline (0.3) with a term-frequency component that rewards
    relations appearing frequently in the subgraph, up to a maximum of 3.0.

    Args:
        relation_name: The relation name to score.
        stats: Aggregated subgraph statistics.

    Returns:
        A quality score between 0.3 and 3.0 (inclusive).
    """
    freq = stats.relation_freq.get(relation_name, 0)
    max_freq = max(stats.relation_freq.values(), default=1)
    tf_score = freq / max_freq
    return 0.3 + tf_score * 2.7


# --- Module-level constants ---

DEFAULT_RELATION_NAMES: tuple[str, ...] = (
    "maps-to",
    "part-of",
    "realizes",
    "supports",
    "所属产品",
)

PRIORITY_TERM_TYPES: frozenset[str] = frozenset(
    {"Concept", "Methodology", "TechComponent", "Ability", "Feature", "Operation"}
)

MAX_EDGES: int = 2000
"""邻接表最大边数，超出后停止 CTE 加载。"""

HUB_THRESHOLD: int = 50
"""Threshold for node degree above which a node is considered a hub."""
