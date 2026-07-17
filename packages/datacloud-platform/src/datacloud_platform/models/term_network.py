"""Term connection network graph data structures.

Data models for source-target term connection network computation:
resolved terms, graph edges, BFS paths, bridge nodes, knowledge refs,
connection summary, and gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
class Gap:
    """A term that could not be resolved during seed resolution."""

    term: str
    reason: str  # "no_exact_match"
    resolution: str  # "unresolved"
    resolved_term_name: str = ""


# ── Path output types ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PathNode:
    """A term node appearing on a connection path."""

    term_id: str
    term_name: str
    term_type: str
    kb_id: str
    kb_file_path: str


@dataclass(frozen=True, slots=True)
class PathEdge:
    """An edge on a connection path."""

    source_term_id: str
    target_term_id: str
    relation_name: str


@dataclass(slots=True)
class Path:
    """A single connection path between a source and target term.

    Attributes:
        path_id: Unique path identifier (e.g. "p1").
        depth: Number of edges (hops) in the path.
        score: Relevance score for sorting.
        readable_path: Human-readable path string (e.g. "A --[maps-to]--> B").
        nodes: Ordered list of term nodes on the path.
        edges: Ordered list of edges on the path.
    """

    path_id: str
    depth: int
    score: float
    readable_path: str
    nodes: list[PathNode] = field(default_factory=list)
    edges: list[PathEdge] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class KnowledgeRef:
    """A knowledge base reference for a term appearing on paths."""

    term_id: str
    term_name: str
    term_type: str
    kb_id: str
    kb_file_path: str
    path_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConnectionSummary:
    """Summary of the connection network for Agent consumption."""

    one_sentence: str = ""
    writing_claim: str = ""


# ── Module-level constants ───────────────────────────────────────────────────

DEFAULT_RELATION_NAMES: tuple[str, ...] = (
    "maps-to",
    "part-of",
    "realizes",
    "supports",
    "所属产品",
)

MAX_EDGES: int = 2000
"""Maximum edges to load into adjacency. Stop CTE loading beyond this."""

HUB_THRESHOLD: int = 50
"""Node degree threshold for hub penalty in path scoring."""

# Relation weight multipliers for path scoring (1.4.4).
RELATION_WEIGHTS: dict[str, float] = {
    "maps-to": 2.0,
    "part-of": 1.0,
    "realizes": 1.0,
    "supports": 0.5,
    "所属产品": 0.5,
}

# Nodes matching these name patterns get a generic-penalty in path scoring.
GENERIC_NODE_PENALTY_PATTERNS: tuple[str, ...] = ("ByDC",)
