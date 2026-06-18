"""Fake Backend implementations for testing — in-memory, no external dependencies.

Usage::

    from fakes import (
        FakeOntologyBackend,
        FakeKnowledgeBackend,
        FakeExecutionBackend,
        FakeStorageBackend,
    )

    onto = FakeOntologyBackend()
    onto._objects["obj1"] = ObjectSummary(object_code="obj1", object_name="Object 1")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from datacloud_platform.models import (
    DimensionProperty,
    EmbeddingHit,
    MatchCandidate,
    MatchResult,
    ObjectSummary,
    ParsedOwlContent,
    ReferenceProperty,
    ScoreUpdateRecord,
    StoredFile,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datacloud_platform.backends.ontology import OntologyQueryable


class _FakeOntologyQueryable:
    """Fake OntologyQueryable for testing — holds objects dict as _classes."""

    _classes: dict[str, Any]
    _relations: list[Any]
    _views: dict[str, Any] | None

    def __init__(self, objects: dict[str, ObjectSummary] | None = None) -> None:
        self._classes = objects or {}
        self._relations = []
        self._views = None


class FakeOntologyBackend:
    """In-memory ontology backend — no datacloud-data SDK dependency.

    Test code can preset ``_objects`` and ``_parsed`` to control behaviour.
    """

    def __init__(self) -> None:
        self._objects: dict[str, ObjectSummary] = {}
        self._parsed: ParsedOwlContent | None = None
        self._tables_created: list[str] = []
        self._tables_dropped: list[str] = []
        self._created_objects: list[tuple[Any, Any, Any]] = []
        self._updated_objects: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_objects: list[tuple[Any, Any, str]] = []
        self._readonly: bool = False
        """When True, create_object / update_object / delete_object raise PermissionError.
        Used to simulate REMOTE backend write-protection behaviour."""

    def parse_owl(self, directory: Path) -> ParsedOwlContent:  # noqa: ARG002
        """Return preset _parsed or empty ParsedOwlContent."""
        return self._parsed or ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Return a FakeOntologyQueryable wrapping _objects."""
        return _FakeOntologyQueryable(self._objects)

    def load_terms(
        self,
        loader: OntologyQueryable,
        *,
        library_id: str = "PERSONAL_LIB",  # noqa: ARG002
    ) -> Any:
        """No-op in fake."""
        return None

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Record table creation."""
        self._tables_created.append(object_code)

    def drop_table(self, object_code: str) -> None:
        """Record table drop."""
        self._tables_dropped.append(object_code)

    def get_objects(
        self,
        loader: OntologyQueryable,
        _base_id: str,
        _scene_id: str,
    ) -> list[ObjectSummary]:
        """Return all objects from _objects."""
        return list(self._objects.values())

    def get_object_detail(
        self,
        loader: OntologyQueryable,
        object_code: str,
    ) -> ObjectSummary | None:
        """Look up object by code in _objects."""
        return self._objects.get(object_code)

    # -- Object CRUD --

    def create_object(self, base_id: str, scene_id: str, obj: Any) -> Any:  # noqa: ARG002
        """Record created object and return it."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_objects.append((base_id, scene_id, obj))
        return obj

    def update_object(  # noqa: ARG002
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Record updated object and return it."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_objects.append((base_id, scene_id, object_code, obj))
        return obj

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        """Record deleted object."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_objects.append((base_id, scene_id, object_code))


class FakeKnowledgeBackend:
    """In-memory knowledge backend — no datacloud-knowledge SDK dependency.

    Test code can preset ``candidates``, ``_disambiguated``, ``_terms``
    and other internal dicts/lists to control behaviour.
    """

    def __init__(self) -> None:
        self._terms: dict[tuple[str, str], str] = {}
        self._terms_by_ids: dict[tuple[str, str, str], str] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._search_results: list[EmbeddingHit] = []
        self.candidates: list[MatchCandidate] = []
        self._disambiguated: list[MatchResult] = []
        self._synced: list[str] = []
        self._removed: list[str] = []
        self._scorerecords: list[ScoreUpdateRecord] = []
        self._type_codes: list[str] = []
        self._ontology_search_results: dict[str, Any] = {}
        self._graph_results: dict[str, Any] = {"nodes": [], "edges": []}

    # -- Search --

    def search_candidates(
        self,
        query: str,  # noqa: ARG002
        *,
        scope: str = "all",  # noqa: ARG002
        limit: int = 20,  # noqa: ARG002
    ) -> list[MatchCandidate]:
        """Return preset candidates."""
        return list(self.candidates)

    def disambiguate(
        self,
        candidates: list[MatchCandidate],
        query: str,  # noqa: ARG002
    ) -> list[MatchResult]:
        """Return preset _disambiguated."""
        return list(self._disambiguated)

    # -- Clarification --

    def prepare_clarification(
        self,
        query: str,  # noqa: ARG002
        slots: list[dict[str, Any]],  # noqa: ARG002
    ) -> dict[str, Any]:
        """Return empty dict."""
        return {}

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Return empty dict."""
        return {}

    # -- Term CRUD --

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        _entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,  # noqa: ARG002
    ) -> None:
        """Record sync call."""
        self._synced.append(entity_code)

    def remove_terms(self, entity_code: str) -> None:
        """Record remove call."""
        self._removed.append(entity_code)

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Look up term name by (code, type_code)."""
        return self._terms.get((term_code, term_type_code))

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Check if term is in _terms."""
        return (term_code, term_type_code) in self._terms

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Batch lookup by (library_id, type_code, term_code) -> term_id."""
        return {k: v for k, v in self._terms_by_ids.items() if k in keys}

    def get_type_codes_by_category(
        self,
        categories: list[int],  # noqa: ARG002
    ) -> list[str]:
        """Return preset _type_codes."""
        return list(self._type_codes)

    # -- Vector --

    def embed(self, text: str) -> list[float]:
        """Return preset embedding or a zero-vector."""
        return self._embeddings.get(text, [0.0] * 768)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return preset embeddings or zero-vectors."""
        return [self.embed(t) for t in texts]

    def search_by_embedding(
        self,
        vector: list[float],  # noqa: ARG002
        term_types: list[str],  # noqa: ARG002
        limit: int = 20,  # noqa: ARG002
    ) -> list[EmbeddingHit]:
        """Return preset _search_results, capped at limit."""
        return self._search_results[:limit]

    # -- Dimension resolution --

    def resolve_dimension_value(
        self,
        value_term_id: str,  # noqa: ARG002
    ) -> DimensionProperty:
        """Return empty DimensionProperty."""
        return DimensionProperty(property_code="", object_code="")

    def get_referenced_by(
        self,
        value_term_id: str,  # noqa: ARG002
    ) -> list[ReferenceProperty]:
        """Return empty list."""
        return []

    def resolve_object_for_property(
        self,
        property_code: str,  # noqa: ARG002
    ) -> str | None:
        """Return None (not resolved)."""
        return None

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
        """Return preset _ontology_search_results or empty dict."""
        return dict(self._ontology_search_results)

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
        """Return preset _graph_results."""
        return dict(self._graph_results)

    # -- Scoring --

    def update_scores(self, records: list[ScoreUpdateRecord]) -> None:
        """Record score updates."""
        self._scorerecords.extend(records)


class FakeExecutionBackend:
    """In-memory execution backend — captures executed actions and tool definitions."""

    def __init__(self) -> None:
        self._executed: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []

    def execute_action(self, action: Any, context: Any, **params: Any) -> Any:  # noqa: ARG002
        """Record execution and return ok status."""
        self._executed.append({"action": action, "params": params})
        return {"status": "ok"}

    def generate_action_tools(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Return preset _tools."""
        return list(self._tools)

    def generate_dynamic_query_tools(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_virtual_actions(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_plan(
        self,
        query: str,
        loader: OntologyQueryable,
        context: Any,
    ) -> Any:
        """Return empty steps plan."""
        return {"steps": []}


class FakeStorageBackend:
    """In-memory file storage backend."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def store_result(
        self,
        key: str,
        data: bytes,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store data and return auto-generated file_id."""
        file_id = str(uuid4())
        self._files[file_id] = data
        if metadata is not None:
            self._meta[file_id] = metadata
        return file_id

    def get_result(self, file_id: str) -> bytes:
        """Return file content by id."""
        return self._files[file_id]

    def delete_result(self, file_id: str) -> None:
        """Remove file by id (no-op if missing)."""
        self._files.pop(file_id, None)
        self._meta.pop(file_id, None)

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List all files, optionally filtered by prefix."""
        return [
            StoredFile(file_id=k, key=k, size_bytes=len(v), created_at="")
            for k, v in self._files.items()
            if k.startswith(prefix)
        ]
