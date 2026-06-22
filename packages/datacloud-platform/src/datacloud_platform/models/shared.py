"""Shared type definitions (Port layer type model).

Protocol signatures forbid bare dict; all return values use frozen dataclasses
defined in this module. mypy provides compile-time protection for new backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObjectSummary:
    """Ontology object summary (list view)."""

    object_code: str
    object_name: str
    description: str = ""
    object_source: str = ""
    field_count: int = 0
    action_count: int = 0


@dataclass(frozen=True)
class ViewSummary:
    """View summary."""

    view_code: str
    view_name: str
    description: str = ""
    object_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationSummary:
    """Relation summary."""

    relation_code: str
    source_object_code: str
    target_object_code: str
    description: str = ""
    relation_cardinality: str = ""


@dataclass(frozen=True)
class ParsedOwlContent:
    """OWL parse result."""

    objects: list[dict[str, Any]] = field(default_factory=list)
    views: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EmbeddingHit:
    """Vector search hit."""

    term_code: str
    term_type_code: str
    name_text: str
    score: float


@dataclass(frozen=True)
class DimensionProperty:
    """Dimension value -> property resolution result."""

    property_code: str
    object_code: str


@dataclass(frozen=True)
class ReferenceProperty:
    """Referencing side of a property."""

    property_code: str
    property_name: str
    object_code: str
    object_name: str


@dataclass(frozen=True)
class StoredFile:
    """Stored file summary."""

    file_id: str
    key: str
    size_bytes: int
    created_at: str


@dataclass(frozen=True)
class MatchCandidate:
    """Term match candidate.

    Fields match datacloud_knowledge.contracts.types.MatchCandidate.
    Adapters handle mapping.
    """

    term_id: str
    term_name: str
    term_type_code: str
    match_type: str
    confidence: float
    score: float


@dataclass(frozen=True)
class MatchResult:
    """Term match result."""

    exact: dict[str, tuple[MatchCandidate, ...]]
    fuzzy: dict[str, tuple[MatchCandidate, ...]]


@dataclass(frozen=True)
class ScoreUpdateRecord:
    """Score feedback loop update record."""

    name_id: str
    success: bool
