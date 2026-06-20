"""KnowledgeBackend Protocol — term retrieval, vector search, disambiguation, clarification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.models.shared import (
        DimensionProperty,
        EmbeddingHit,
        MatchCandidate,
        MatchResult,
        ReferenceProperty,
        ScoreUpdateRecord,
    )


class KnowledgeBackend(Protocol):
    """Term retrieval, vector search, disambiguation, clarification."""

    # -- Search --

    def search_candidates(
        self, query: str, *, scope: str = "all", limit: int = 20
    ) -> list[MatchCandidate]:
        """Multi-strategy candidate search (BM25 + semantic + fuzzy)."""
        ...

    def disambiguate(
        self,
        candidates: list[MatchCandidate],
        query: str,
    ) -> list[MatchResult]:
        """Candidate disambiguation."""
        ...

    # -- Clarification --

    def prepare_clarification(
        self, query: str, slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Prepare clarification flow. Returns unstable structure (LLM output), keep as dict."""
        ...

    def finalize_clarification(
        self,
        *,
        query: str,
        ontology_code: str,
        structured_input: dict[str, Any],
        mode: str,
        needs_clarification: bool,
        form: Any = None,
        metadata: Any = None,
        user_id: str | None = None,
        persist_confirmed_synonyms: bool = True,
        language: str = "zh_CN",
    ) -> dict[str, Any]:
        """Complete clarification, return resolved result with structured_input and persisted_synonyms."""
        ...

    # -- Term CRUD --

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Sync object term metadata."""
        ...

    def remove_terms(self, entity_code: str) -> None:
        """Remove all terms associated with an object."""
        ...

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Look up term display name by code + type."""
        ...

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Check if term exists."""
        ...

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Batch lookup: (library_id, type_code, term_code) -> term_id."""
        ...

    def get_type_codes_by_category(self, categories: list[int]) -> list[str]:
        """Get term type code list under given categories."""
        ...

    # -- Vector --

    def embed(self, text: str) -> list[float]:
        """Text -> vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch text -> vector."""
        ...

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[EmbeddingHit]:
        """Vector similarity search for terms."""
        ...

    # -- Dimension resolution --

    def resolve_dimension_value(self, value_term_id: str) -> DimensionProperty:
        """Dimension value -> property + object."""
        ...

    def get_referenced_by(self, value_term_id: str) -> list[ReferenceProperty]:
        """Get list of properties referencing this enum/dimension value."""
        ...

    def resolve_object_for_property(self, property_code: str) -> str | None:
        """Property -> owning object code."""
        ...

    # -- Ontology search & graph --

    def search_ontology(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search ontology metadata and instances via vector / keyword.

        Returns structure is consumer-facing JSON, kept as dict.
        """
        ...

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Batch search across all scenes of a base, aggregating + deduplicating results.

        Returns same structure as :meth:`search_ontology`:
        ``{"metadata": [...], "instances": [...], "totalCount": {...}}``.
        """
        ...

    def graph_query(
        self,
        base_id: str,
        scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict[str, Any]:
        """Graph traversal query returning nodes + edges.

        Returns structure is consumer-facing JSON, kept as dict.
        Optional: backends without graph support may not implement this.
        """
        ...

    # -- Scoring --

    def update_scores(self, records: list[ScoreUpdateRecord]) -> None:
        """Batch update term scores."""
        ...

    # -- Instance search & graph path --

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search instances in a base. Returns ``{"data": [...], "totalCount": N}``."""
        ...

    def graph_path(
        self,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Find shortest path between two objects.
        Returns ``{"path": [...], "edges": [...], "hops": N}``."""
        ...

    # -- Field aliases & clarification results --

    def resolve_field_aliases(
        self, field_aliases: dict[str, list[str]]
    ) -> dict[str, list[tuple[str, str]]]:
        """Resolve field aliases to (actual_field, confidence_score) tuples."""
        ...

    def store_clarification_results(
        self, results: dict[str, Any], user_id: str
    ) -> list[str]:
        """Store clarification results, return stored record IDs."""
        ...
