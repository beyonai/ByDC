"""DataCloudKnowledgeBackend — KnowledgeBackend via datacloud-knowledge SDK."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.models.shared import (
    DimensionProperty,
    EmbeddingHit,
    MatchCandidate,
    MatchResult,
    ReferenceProperty,
    ScoreUpdateRecord,
)

logger = logging.getLogger(__name__)


class DataCloudKnowledgeBackend:
    """KnowledgeBackend via datacloud-knowledge SDK.

    Lazily initialises reader, search engine, and embedding service on
    first use so that the package does not require a running database
    at import time.
    """

    def __init__(self) -> None:
        self._reader: Any = None
        self._search_engine: Any = None
        self._embedding: Any = None

    # ── internal init helpers ──────────────────────────────────────────────

    def _get_reader(self) -> Any:
        if self._reader is None:
            from datacloud_knowledge.adapters import create_reader  # noqa: PLC0415

            self._reader = create_reader()
        return self._reader

    def _get_search_engine(self) -> Any:
        if self._search_engine is None:
            from datacloud_knowledge.adapters.opengauss.engine import (  # noqa: PLC0415
                PostgresSearchEngine,
            )

            self._search_engine = PostgresSearchEngine()
        return self._search_engine

    def _get_embedding(self) -> Any:
        if self._embedding is None:
            from datacloud_knowledge.retrieval.embedding.service import (  # noqa: PLC0415
                EmbeddingService,
            )

            self._embedding = EmbeddingService()
        return self._embedding

    # ── Search ─────────────────────────────────────────────────────────────

    def search_candidates(
        self, query: str, *, _scope: str = "all", limit: int = 20
    ) -> list[MatchCandidate]:
        """Multi-strategy candidate search (BM25 + semantic + fuzzy).

        Delegates to ``search_all_candidates_with_name_id`` from the
        datacloud-knowledge SDK, then converts the result dict into a
        flat list of typed :class:`MatchCandidate` models.

        Args:
            query: The search query string.
            scope: Search scope (passed through to SDK, default ``all``).
            limit: Maximum number of results.

        Returns:
            Flattened list of MatchCandidate across all concept terms.
        """
        from datacloud_knowledge.retrieval.candidate_search import (  # noqa: PLC0415
            search_all_candidates_with_name_id,
        )

        if not query.strip():
            return []

        raw: dict[str, list[dict[str, Any]]] = search_all_candidates_with_name_id(
            [query], top_k=limit
        )
        result: list[MatchCandidate] = []
        for candidates in raw.values():
            result.extend(
                MatchCandidate(
                    term_id=str(c.get("term_id", "")),
                    term_name=str(c.get("term_name", "")),
                    term_type_code=str(c.get("term_type_code", "")),
                    match_type=str(c.get("match_type", "")),
                    confidence=float(c.get("confidence", 0)),
                    score=float(c.get("score", 0)),
                )
                for c in candidates
            )
        return result[:limit]

    def disambiguate(
        self, candidates: list[MatchCandidate], query: str
    ) -> list[MatchResult]:
        """Candidate disambiguation via the knowledge SDK.

        Groups flat candidates into SDK ``MatchResult``, calls the
        SDK ``disambiguate`` function, and converts the result back
        to platform model types.

        Args:
            candidates: Flat list from :meth:`search_candidates`.
            query: Original query (for context).

        Returns:
            A single-element list containing the disambiguated
            :class:`MatchResult`.
        """
        from datacloud_knowledge.contracts.types import (  # noqa: PLC0415
            MatchCandidate as SdkMatchCandidate,
        )
        from datacloud_knowledge.contracts.types import (  # noqa: PLC0415
            MatchResult as SdkMatchResult,
        )
        from datacloud_knowledge.intent import (  # noqa: PLC0415
            disambiguate as sdk_disambiguate,
        )

        if not candidates:
            return [MatchResult(exact={}, fuzzy={})]

        # Group platform candidates by match_type for SDK MatchResult
        exact_cands: list[SdkMatchCandidate] = []
        fuzzy_cands: list[SdkMatchCandidate] = []
        for c in candidates:
            sdk_c = SdkMatchCandidate(
                term_id=c.term_id,
                term_name=c.term_name,
                term_type_code=c.term_type_code,
                match_type=c.match_type,
                confidence=c.confidence,
                score=c.score,
            )
            if c.match_type == "exact":
                exact_cands.append(sdk_c)
            else:
                fuzzy_cands.append(sdk_c)

        key = query or "query"
        sdk_match = SdkMatchResult(
            exact={key: tuple(exact_cands)},
            fuzzy={key: tuple(fuzzy_cands)},
        )

        sdk_result = sdk_disambiguate(
            match_result=sdk_match,
            session=None,
        )

        # Convert DisambiguationResult → platform MatchResult
        platform_exact: dict[str, tuple[MatchCandidate, ...]] = {}
        platform_fuzzy: dict[str, tuple[MatchCandidate, ...]] = {}

        for mention_text, sdk_c in sdk_result.confirmed.items():
            platform_c = MatchCandidate(
                term_id=sdk_c.term_id,
                term_name=sdk_c.term_name,
                term_type_code=sdk_c.term_type_code,
                match_type=sdk_c.match_type,
                confidence=sdk_c.confidence,
                score=sdk_c.score,
            )
            platform_exact[mention_text] = (platform_c,)

        for mention_text, sdk_cs in sdk_result.ambiguous.items():
            platform_cs = tuple(
                MatchCandidate(
                    term_id=sc.term_id,
                    term_name=sc.term_name,
                    term_type_code=sc.term_type_code,
                    match_type=sc.match_type,
                    confidence=sc.confidence,
                    score=sc.score,
                )
                for sc in sdk_cs
            )
            platform_fuzzy[mention_text] = platform_cs

        return [MatchResult(exact=platform_exact, fuzzy=platform_fuzzy)]

    # ── Clarification ──────────────────────────────────────────────────────

    def prepare_clarification(
        self, query: str, slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Prepare clarification flow.

        Wraps the SDK ``prepare_query_clarification`` and serialises
        the result to a dict (structure is LLM-driven and unstable).

        Args:
            query: User query text.
            slots: Structured query slots.

        Returns:
            Clarification analysis as a dict.
        """
        from datacloud_knowledge.intent.types import ClarificationMode  # noqa: PLC0415
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            prepare_query_clarification as sdk_prepare,
        )

        structured_input: dict[str, Any] = (
            {"slots": slots} if slots else {"query": query}
        )
        analysis = sdk_prepare(
            query=query,
            ontology_code="",
            structured_input=structured_input,
            mode=ClarificationMode.QUERY,
        )
        return {
            "needs_clarification": analysis.needs_clarification,
            "form": analysis.form,
            "metadata": analysis.metadata,
        }

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:
        """Complete clarification, return resolved result.

        Args:
            clarification_id: Clarification session identifier.

        Returns:
            Resolved structured input as dict.
        """
        _ = clarification_id
        logger.warning(
            "finalize_clarification is a no-op: the SDK function requires "
            "full structured_input which cannot be reconstructed from "
            "clarification_id alone. Consider calling "
            "datacloud_knowledge.provider.finalize_query_clarification directly."
        )
        return {}

    # ── Term CRUD ──────────────────────────────────────────────────────────

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Sync object term metadata into the knowledge DB.

        Args:
            entity_code: Object code.
            entity_name: Human-readable object name.
            entity_source: Source type (e.g. ``DYNAMIC_TABLE``).
            fields: Property definitions.
            backfill_vectors: Whether to rebuild tsvector + embedding.
        """
        from datacloud_knowledge.ingestion.term_sync import sync_object_terms  # noqa: PLC0415

        sync_object_terms(
            entity_code=entity_code,
            entity_name=entity_name,
            entity_source=entity_source,
            fields=fields,
            backfill_vectors=backfill_vectors,
        )

    def remove_terms(self, entity_code: str) -> None:
        """Remove all terms associated with an object.

        Args:
            entity_code: Object code.
        """
        from datacloud_knowledge.ingestion.term_sync import remove_object_terms  # noqa: PLC0415

        remove_object_terms(entity_code)

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Look up term display name by code + type.

        Args:
            term_code: Term identifier.
            term_type_code: Term type code (e.g. ``object``, ``prop``).

        Returns:
            Display name or None.
        """
        reader = self._get_reader()
        try:
            return reader.get_term(  # type: ignore[no-any-return]
                term_code=term_code,
                term_type_code=term_type_code,
            )
        except Exception:
            logger.exception("get_term failed term_code=%s", term_code)
            return None

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Check if a term exists in the knowledge DB.

        Args:
            term_code: Term identifier.
            term_type_code: Term type code.

        Returns:
            True if the term exists.
        """
        reader = self._get_reader()
        try:
            return bool(
                reader.term_exists(term_code=term_code, term_type_code=term_type_code)
            )
        except Exception:
            logger.exception("term_exists failed term_code=%s", term_code)
            return False

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Batch lookup: (library_id, type_code, term_code) → name_id.

        Args:
            keys: List of (library_id, type_code, term_code) tuples.

        Returns:
            Mapping from key tuple to resolved name_id.
        """
        reader = self._get_reader()
        try:
            return reader.get_term_by_ids(keys=keys)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_by_ids failed with %d keys", len(keys))
            return {}

    def get_type_codes_by_category(self, categories: list[int]) -> list[str]:
        """Get term type code list under given categories.

        Args:
            categories: Category IDs (e.g. ``[1, 2]`` for instance types).

        Returns:
            List of matching term type codes.
        """
        reader = self._get_reader()
        try:
            result: set[str] = reader.get_type_codes_by_category(
                categories=set(categories)
            )
            return sorted(result)
        except Exception:
            logger.exception(
                "get_type_codes_by_category failed categories=%s", categories
            )
            return []

    # ── Vector ─────────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """Text → embedding vector.

        Args:
            text: Input text.

        Returns:
            Embedding vector as list of floats.
        """
        svc = self._get_embedding()
        return svc.get_text_embedding(text)  # type: ignore[no-any-return]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch text → embedding vectors.

        Args:
            texts: Input texts.

        Returns:
            List of embedding vectors.
        """
        svc = self._get_embedding()
        return svc.get_text_embedding_batch(texts)  # type: ignore[no-any-return]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[EmbeddingHit]:
        """Vector similarity search for terms.

        Args:
            vector: Query embedding vector.
            term_types: Filter term type codes (e.g. ``['object', 'view']``).
            limit: Maximum results.

        Returns:
            List of typed :class:`EmbeddingHit` models.
        """
        engine = self._get_search_engine()
        raw: list[dict[str, Any]] = engine.search_terms_by_embedding(
            vector=vector,
            term_types=term_types,
            limit=limit,
        )
        return [
            EmbeddingHit(
                term_code=str(h["term_code"]),
                term_type_code=str(h["term_type_code"]),
                name_text=str(h.get("name_text", h.get("term_name", ""))),
                score=round(float(h["score"]), 4),
            )
            for h in raw
        ]

    # ── Dimension resolution ───────────────────────────────────────────────

    def resolve_dimension_value(self, value_term_id: str) -> DimensionProperty:
        """Dimension value → property + object.

        Args:
            value_term_id: The dimension value term ID.

        Returns:
            :class:`DimensionProperty` with property_code and object_code.
        """
        from datacloud_knowledge.retrieval.dimension_values import (  # noqa: PLC0415
            DimensionValueResolver,
        )

        raw: dict[str, str] = DimensionValueResolver().resolve_value_to_property(
            value_term_id
        )
        return DimensionProperty(
            property_code=raw.get("propertyCode", ""),
            object_code=raw.get("objectCode", ""),
        )

    def get_referenced_by(self, value_term_id: str) -> list[ReferenceProperty]:
        """Get list of properties referencing this enum/dimension value.

        Args:
            value_term_id: The value term ID.

        Returns:
            List of :class:`ReferenceProperty` models.
        """
        from datacloud_knowledge.retrieval.dimension_values import (  # noqa: PLC0415
            DimensionValueResolver,
        )

        raw: list[dict[str, str]] = DimensionValueResolver().get_referenced_by(
            value_term_id
        )
        return [
            ReferenceProperty(
                property_code=r.get("propertyCode", r.get("property_code", "")),
                property_name=r.get("propertyName", r.get("property_name", "")),
                object_code=r.get("objectCode", r.get("object_code", "")),
                object_name=r.get("objectName", r.get("object_name", "")),
            )
            for r in raw
        ]

    def resolve_object_for_property(self, property_code: str) -> str | None:
        """Property → owning object code.

        Args:
            property_code: Property term identifier.

        Returns:
            Object code string, or None if not found.
        """
        from datacloud_knowledge.retrieval.owl_relation_resolver import (  # noqa: PLC0415
            resolve_object_for_property as sdk_resolve,
        )

        return sdk_resolve(property_code)  # type: ignore[no-any-return]

    # ── Ontology search & graph ────────────────────────────────────────────

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Batch search across all scenes of a base.

        Performs a global vector search via the knowledge SDK embedding
        service and search engine, then caps results at ``limit`` and
        deduplicates by ``(termCode, termType)``.

        Args:
            base_id: Ontology base identifier.
            keyword: Search keyword string.
            limit: Max results per branch (metadata / instances).

        Returns:
            ``{"metadata": [...], "instances": [...], "totalCount": {...}}``
        """
        _ = base_id

        if not keyword:
            return {
                "metadata": [],
                "instances": [],
                "totalCount": {"metadata": 0, "instances": 0},
            }

        svc = self._get_embedding()
        vec = svc.get_text_embedding(keyword)

        result: dict[str, Any] = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        engine = self._get_search_engine()

        # Metadata branch
        _METADATA_TERM_TYPES = {
            "object",
            "view",
            "dimension",
            "property",
            "ontology_action",
        }
        metadata_hits = engine.search_terms_by_embedding(
            vector=vec,
            term_types=list(_METADATA_TERM_TYPES),
            limit=limit,
        )
        seen_metadata: set[tuple[str, str]] = set()
        for hit in metadata_hits:
            key = (str(hit["term_code"]), str(hit["term_type_code"]))
            if key in seen_metadata:
                continue
            seen_metadata.add(key)
            result["metadata"].append(
                {
                    "termCode": str(hit["term_code"]),
                    "termType": str(hit["term_type_code"]),
                    "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                    "score": round(float(hit["score"]), 4),
                }
            )
        result["totalCount"]["metadata"] = len(result["metadata"])

        # Instance branch
        reader = self._get_reader()
        instance_type_codes: list[str] = []
        try:
            instance_type_codes = sorted(
                reader.get_type_codes_by_category(categories={3, 4, 5})
            )
        except Exception:
            logger.exception(
                "Failed to get instance type codes for search_ontology_batch"
            )

        if instance_type_codes:
            instance_hits = engine.search_terms_by_embedding(
                vector=vec,
                term_types=instance_type_codes,
                limit=limit,
            )
            seen_instances: set[tuple[str, str]] = set()
            for hit in instance_hits:
                key = (str(hit["term_code"]), str(hit["term_type_code"]))
                if key in seen_instances:
                    continue
                seen_instances.add(key)
                result["instances"].append(
                    {
                        "termCode": str(hit["term_code"]),
                        "termType": str(hit["term_type_code"]),
                        "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                        "score": round(float(hit["score"]), 4),
                    }
                )
            result["totalCount"]["instances"] = len(result["instances"])

        return result

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
        """Unified vector search across metadata and instance terms.

        Uses the knowledge SDK embedding service and search engine to
        perform cosine-similarity vector search across both metadata
        term types and instance term types within a scene.

        Args:
            base_id: Ontology base identifier.
            scene_id: Scene identifier (``-1`` for all scenes).
            keyword: Search keyword string.
            query_type: Search mode (``vector``, reserved).
            search_scope: ``metadata`` / ``instance`` / ``all``.
            **kwargs: Additional search parameters (passed through).

        Returns:
            ``{"metadata": [...], "instances": [...], "totalCount": {...}}``
        """
        _ = base_id, scene_id, query_type, kwargs

        if not keyword:
            return {
                "metadata": [],
                "instances": [],
                "totalCount": {"metadata": 0, "instances": 0},
            }

        svc = self._get_embedding()
        vec = svc.get_text_embedding(keyword)

        result: dict[str, Any] = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        engine = self._get_search_engine()

        # Metadata branch
        if search_scope in ("metadata", "all"):
            _METADATA_TERM_TYPES = {
                "object",
                "view",
                "dimension",
                "property",
                "ontology_action",
            }
            metadata_hits = engine.search_terms_by_embedding(
                vector=vec,
                term_types=list(_METADATA_TERM_TYPES),
                limit=20,
            )
            result["metadata"] = [
                {
                    "termCode": hit["term_code"],
                    "termType": hit["term_type_code"],
                    "nameText": hit.get("name_text", hit.get("term_name", "")),
                    "score": round(float(hit["score"]), 4),
                }
                for hit in metadata_hits
            ]
            result["totalCount"]["metadata"] = len(result["metadata"])

        # Instance branch
        if search_scope in ("instance", "all"):
            reader = self._get_reader()
            instance_type_codes: list[str] = []
            try:
                instance_type_codes = sorted(
                    reader.get_type_codes_by_category(
                        categories={3, 4, 5},
                    )
                )
            except Exception:
                logger.exception(
                    "Failed to get instance type codes for search_ontology"
                )

            if instance_type_codes:
                instance_hits = engine.search_terms_by_embedding(
                    vector=vec,
                    term_types=instance_type_codes,
                    limit=20,
                )
                result["instances"] = [
                    {
                        "termCode": hit["term_code"],
                        "termType": hit["term_type_code"],
                        "nameText": hit.get("name_text", hit.get("term_name", "")),
                        "score": round(float(hit["score"]), 4),
                    }
                    for hit in instance_hits
                ]
                result["totalCount"]["instances"] = len(result["instances"])

        return result

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
        """Graph traversal query — local adapter does not support graph yet.

        Returns empty nodes/edges. For graph support, use the
        ``datacloud-server`` local adapter directly, or configure a
        remote ontology backend with graph capabilities.

        Args:
            base_id: Ontology base identifier.
            scene_id: Scene identifier.
            object_code: Filter to specific object codes.
            match_by: Match mode (reserved).
            values: Match values (reserved).
            step: Maximum hop depth (reserved).

        Returns:
            ``{"nodes": [], "edges": []}``
        """
        _ = base_id, scene_id, object_code, match_by, values, step
        logger.debug(
            "graph_query not implemented in knowledge adapter — returning empty result"
        )
        return {"nodes": [], "edges": []}

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search instances in a base — not yet implemented.

        Returns empty result. For instance search, use the
        ``datacloud-server`` local adapter directly.

        Args:
            base_id: Ontology base identifier.
            object_code: Object code filter.
            select: Optional field selection.
            where: Optional where clause.

        Returns:
            ``{"data": [], "totalCount": 0}``
        """
        _ = base_id, object_code, select, where
        logger.debug(
            "search_instances not implemented in knowledge adapter — "
            "returning empty result"
        )
        return {"data": [], "totalCount": 0}

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
        """Find shortest path between two objects — not yet implemented.

        Returns empty path. For graph path queries, use the
        ``datacloud-server`` local adapter directly.

        Args:
            base_id: Ontology base identifier.
            scene_id: Scene identifier.
            match_by: Match mode (reserved).
            start_node: Starting object code.
            end_node: Target object code (empty = return all paths).
            direction: Path direction (``forward`` / ``backward``).

        Returns:
            ``{"path": [], "edges": [], "hops": -1}``
        """
        _ = base_id, scene_id, match_by, start_node, end_node, direction
        logger.debug(
            "graph_path not implemented in knowledge adapter — returning empty result"
        )
        return {"path": [], "edges": [], "hops": -1}

    # ── Scoring ────────────────────────────────────────────────────────────

    def update_scores(self, records: list[ScoreUpdateRecord]) -> None:
        """Batch update term scores.

        Args:
            records: List of :class:`ScoreUpdateRecord` to apply.
        """
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415
        from datacloud_knowledge.intent.score_update import (  # noqa: PLC0415
            batch_update_scores as sdk_batch_update,
        )
        from datacloud_knowledge.intent.types import (  # noqa: PLC0415
            ScoreUpdateRecord as SdkScoreUpdateRecord,
        )

        sdk_records = tuple(
            SdkScoreUpdateRecord(name_id=r.name_id, success=r.success) for r in records
        )
        sdk_batch_update(records=sdk_records, writer=create_writer())
