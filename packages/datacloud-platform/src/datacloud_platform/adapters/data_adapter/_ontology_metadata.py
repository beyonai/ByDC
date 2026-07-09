"""Property resolution, terminology bindings, ontology search & graph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase

logger = logging.getLogger(__name__)


class OntologyMetadataMixin(DataCloudDataBackendBase):
    """Property resolution, terminology bindings, ontology search & graph."""

    # ── OntologyBackend: Terminology bindings ──────────────────────────────

    def get_object_property_term_bindings(
        self,
        object_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info — stub (shadowed by OntologyBackendMixin)."""
        _ = object_codes, base_id
        return []

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info for view properties — stub (shadowed by OntologyBackendMixin)."""
        _ = view_codes, base_id
        return []

    def get_view_included_objects(
        self,
        ontology_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """View included object codes — stub (shadowed by OntologyBackendMixin)."""
        _ = ontology_code, base_id
        return []

    def get_joinkey_related_objects(
        self,
        ontology_code: str,
        field_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[str]:
        """Joinkey related objects — stub (shadowed by OntologyBackendMixin)."""
        _ = ontology_code, field_codes, base_id
        return []

    def resolve_property_name(
        self,
        name_text: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> tuple[str, str] | None:
        """Resolve single property name — stub (shadowed by OntologyBackendMixin)."""
        _ = name_text, scope_code, base_id
        return None

    def resolve_property_names(
        self,
        name_texts: list[str],
        scope_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, tuple[str, str]]:
        """Batch resolve property names — stub (shadowed by OntologyBackendMixin)."""
        _ = name_texts, scope_code, base_id
        return {}

    def get_property_aliases(
        self,
        field_code: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """Get property aliases — stub (shadowed by OntologyBackendMixin)."""
        _ = field_code, scope_code, base_id
        return []

    # ── OntologyBackend: Search & graph (new) ──────────────────────────────

    _ONTOLOGY_TYPE_TO_TERM: dict[str, str] = {
        "object": "object",
        "action": "ontology_action",
        "view": "view",
        "property": "property",
        "dimension": "dimension",
    }

    def search_ontology(
        self,
        base_id: str,
        scene_ids: list[str],
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        ontology_type: list[str] | None = None,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Unified vector search across metadata and instance terms.

        Uses the knowledge SDK embedding service and search engine to
        perform cosine-similarity vector search across metadata and
        instance term types.
        """
        _ = base_id, scene_ids, query_type, kwargs

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

        _ALL_METADATA_TYPES = list(self._ONTOLOGY_TYPE_TO_TERM.values())
        if ontology_type:
            metadata_types = [
                self._ONTOLOGY_TYPE_TO_TERM[t]
                for t in ontology_type
                if t in self._ONTOLOGY_TYPE_TO_TERM
            ]
            if not metadata_types:
                metadata_types = _ALL_METADATA_TYPES
        else:
            metadata_types = _ALL_METADATA_TYPES

        view_code_set: set[str] | None = set(view_code) if view_code else None
        property_code_set: set[str] | None = (
            set(property_code) if property_code else None
        )

        limit = kwargs.get("limit", 20)

        if search_scope in ("metadata", "all"):
            metadata_hits = engine.search_terms_by_embedding(
                vector=vec,
                term_types=metadata_types,
                term_codes=object_code,
                limit=limit,
            )
            for hit in metadata_hits:
                term_code = str(hit.get("term_code", ""))
                term_type = str(hit.get("term_type_code", ""))
                if view_code_set is not None and term_code not in view_code_set:
                    continue
                if property_code_set is not None and term_code not in property_code_set:
                    continue
                entry: dict[str, Any] = {
                    "termCode": term_code,
                    "termType": term_type,
                    "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                    "score": round(float(hit["score"]), 4),
                }
                result["metadata"].append(entry)
            result["totalCount"]["metadata"] = len(result["metadata"])

        if search_scope in ("instance", "all"):
            reader = self._get_knowledge_reader()
            instance_type_codes: list[str] = []
            try:
                instance_type_codes = sorted(
                    reader.get_type_codes_by_category(categories={3, 4, 5})
                )
            except Exception:
                logger.exception(
                    "Failed to get instance type codes for search_ontology"
                )

            if instance_type_codes:
                instance_hits = engine.search_terms_by_embedding(
                    vector=vec,
                    term_types=instance_type_codes,
                    limit=limit,
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

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Batch search across all scenes of a base via vector search."""
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

        reader = self._get_knowledge_reader()
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
        """Graph traversal query — not yet implemented."""
        _ = base_id, scene_id, object_code, match_by, values, step
        return {"nodes": [], "edges": []}

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search instances in a base — not yet implemented."""
        _ = base_id, object_code, select, where
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
        """Find shortest path between two objects — not yet implemented."""
        _ = base_id, scene_id, match_by, start_node, end_node, direction
        return {"path": [], "edges": [], "hops": -1}
