"""No-op backends — return empty/null results, write operations raise PermissionError.

Used as fallback when a backend type has no implementation configured for a base.
"""

from __future__ import annotations

from typing import Any


class _NoopOntologyBackend:
    """Ontology backend where all reads return empty and all writes are forbidden."""

    def parse_owl(self, directory: Any) -> Any:
        """Return empty ParsedOwlContent."""
        from datacloud_platform.models import ParsedOwlContent

        return ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Any) -> Any:
        """Raise PermissionError — no ontology available."""
        raise PermissionError("Ontology not available")

    def load_terms(self, loader: Any, *, library_id: str = "PERSONAL_LIB") -> Any:
        """Return None."""
        return None

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def drop_table(self, object_code: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def get_objects(self, loader: Any, base_id: str, scene_id: str) -> list[Any]:
        """Return empty list."""
        return []

    def get_object_detail(self, loader: Any, object_code: str) -> Any | None:
        """Return None."""
        return None


class _NoopKnowledgeBackend:
    """Knowledge backend where all reads return empty/null and mutations are no-ops."""

    def search_candidates(
        self, query: str, *, scope: str = "all", limit: int = 20
    ) -> list[Any]:
        """Return empty list."""
        return []

    def disambiguate(self, candidates: list[Any], query: str) -> list[Any]:
        """Return empty list."""
        return []

    def prepare_clarification(
        self, query: str, slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return empty dict."""
        return {}

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:
        """Return empty dict."""
        return {}

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """No-op."""

    def remove_terms(self, entity_code: str) -> None:
        """No-op."""

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Return None."""
        return None

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Return False."""
        return False

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Return empty dict."""
        return {}

    def get_type_codes_by_category(self, categories: list[int]) -> list[str]:
        """Return empty list."""
        return []

    def embed(self, text: str) -> list[float]:
        """Return zero vector."""
        return [0.0] * 768

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors."""
        return [[0.0] * 768 for _ in texts]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Return empty list."""
        return []

    def resolve_dimension_value(self, value_term_id: str) -> Any:
        """Return empty DimensionProperty."""
        from datacloud_platform.models import DimensionProperty

        return DimensionProperty(property_code="", object_code="")

    def get_referenced_by(self, value_term_id: str) -> list[Any]:
        """Return empty list."""
        return []

    def resolve_object_for_property(self, property_code: str) -> str | None:
        """Return None."""
        return None

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
        """Return empty search result."""
        return {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

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
        """Return empty graph result."""
        return {"nodes": [], "edges": []}

    def update_scores(self, records: list[Any]) -> None:
        """No-op."""


class _NoopExecutionBackend:
    """Execution backend where all operations are forbidden."""

    def execute_action(self, action: Any, context: Any, **params: Any) -> Any:
        """Raise PermissionError — execution not available."""
        raise PermissionError("Execution not available")

    def generate_action_tools(
        self, loader: Any, mounted_objects: list[str]
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_dynamic_query_tools(
        self, loader: Any, mounted_objects: list[str]
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_virtual_actions(
        self, loader: Any, mounted_objects: list[str]
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_plan(self, query: str, loader: Any, context: Any) -> Any:
        """Return empty plan."""
        return {"steps": []}


class _NoopStorageBackend:
    """Storage backend where all operations are forbidden."""

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def get_result(self, file_id: str) -> bytes:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def delete_result(self, file_id: str) -> None:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def list_results(self, prefix: str = "") -> list[Any]:
        """Return empty list."""
        return []
