"""KnowledgeMixin — search, graph, aliases, and clarification via knowledge backend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from datacloud_platform.backends._contracts import _HasKnowledgeBackend

if TYPE_CHECKING:
    from datacloud_platform.models.shared import MatchResult

logger = logging.getLogger(__name__)


class KnowledgeMixin:
    """Mixin for knowledge-backend-routed operations: search, graph, disambiguation."""

    # ── Knowledge: search / disambiguation ──

    def search(
        self: _HasKnowledgeBackend,
        base_id: str,
        query: str,
        *,
        scope: str = "all",
        limit: int = 20,
    ) -> list[MatchResult]:
        """Term search + disambiguation routed to the knowledge backend."""
        backend = self._knowledge_for(base_id)
        candidates = backend.search_candidates(query, scope=scope, limit=limit)
        return backend.disambiguate(candidates, query)

    def search_ontology(
        self: _HasKnowledgeBackend,
        base_id: str,
        scene_ids: list[str],
        *,
        keyword: str,
        query_type: str = "keyword",
        search_scope: str = "all",
        ontology_type: list[str] | None = None,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search ontology metadata and instances via vector / keyword.

        Returns consumer-facing JSON as dict.
        """
        return self._knowledge_for(base_id).search_ontology(
            base_id,
            scene_ids,
            keyword=keyword,
            query_type=query_type,
            search_scope=search_scope,
            ontology_type=ontology_type,
            object_code=object_code,
            view_code=view_code,
            property_code=property_code,
            **kwargs,
        )

    def search_ontology_batch(
        self: _HasKnowledgeBackend,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Batch search across all scenes of a base, aggregating results.

        Returns consumer-facing JSON as dict with metadata + instances deduplicated.
        """
        return self._knowledge_for(base_id).search_ontology_batch(
            base_id,
            keyword,
            limit=limit,
        )

    def graph_query(
        self: _HasKnowledgeBackend,
        base_id: str,
        scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict[str, Any]:
        """Graph traversal query returning nodes + edges."""
        return self._knowledge_for(base_id).graph_query(
            base_id,
            scene_id,
            object_code=object_code,
            match_by=match_by,
            values=values,
            step=step,
        )

    # ── Search & Graph (knowledge-backend routed) ──

    def search_instances(
        self: _HasKnowledgeBackend,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search instances in a base."""
        return self._knowledge_for(base_id).search_instances(
            base_id, object_code=object_code, select=select, where=where
        )

    def graph_path(
        self: _HasKnowledgeBackend,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Find shortest path between two objects."""
        return self._knowledge_for(base_id).graph_path(
            base_id,
            scene_id,
            match_by=match_by,
            start_node=start_node,
            end_node=end_node,
            direction=direction,
        )

    # ── Field aliases & clarification results ──

    def resolve_field_aliases(
        self: _HasKnowledgeBackend,
        base_id: str,
        field_aliases: dict[str, list[str]],
    ) -> dict[str, list[tuple[str, str]]]:
        """Resolve field aliases to (actual_field, confidence_score) tuples."""
        return self._knowledge_for(base_id).resolve_field_aliases(field_aliases)

    def store_clarification_results(
        self: _HasKnowledgeBackend,
        base_id: str,
        results: dict[str, Any],
        user_id: str,
    ) -> list[str]:
        """Store clarification results, return stored record IDs."""
        return self._knowledge_for(base_id).store_clarification_results(
            results, user_id
        )

    def finalize_clarification(
        self: _HasKnowledgeBackend,
        base_id: str,
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
        """Complete clarification via knowledge backend.

        Returns ``{"structured_input": ..., "persisted_synonyms": ...}``.
        """
        return self._knowledge_for(base_id).finalize_clarification(
            query=query,
            ontology_code=ontology_code,
            structured_input=structured_input,
            mode=mode,
            needs_clarification=needs_clarification,
            form=form,
            metadata=metadata,
            user_id=user_id,
            persist_confirmed_synonyms=persist_confirmed_synonyms,
            language=language,
        )
