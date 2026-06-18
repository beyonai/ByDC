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

from datacloud_platform.models.shared import (
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
        """When True, write operations raise PermissionError."""

        # View tracking
        self._views: dict[str, list[dict[str, Any]]] = {}
        self._created_views: list[tuple[Any, Any, Any]] = []
        self._updated_views: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_views: list[tuple[Any, Any, str]] = []

        # Relation tracking
        self._relations: dict[str, list[dict[str, Any]]] = {}
        self._created_relations: list[tuple[Any, Any, Any]] = []
        self._updated_relations: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_relations: list[tuple[Any, Any, str]] = []

        # Action tracking
        self._actions: dict[str, list[dict[str, Any]]] = {}
        self._created_actions: list[tuple[Any, Any, Any, Any]] = []
        self._updated_actions: list[tuple[Any, Any, Any, Any, Any]] = []
        self._deleted_actions: list[tuple[Any, Any, Any, str]] = []

        # Datasource tracking
        self._datasources: dict[str, list[dict[str, Any]]] = {}
        self._created_datasources: list[tuple[Any, Any, Any]] = []
        self._deleted_datasources: list[tuple[Any, Any, str]] = []

        # Scene tracking
        self._scenes: list[dict[str, Any]] = []
        self._scene_details: dict[str, dict[str, Any]] = {}
        self._ontologies_by_scene: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _empty_scene_details() -> dict[str, Any]:
        """Return empty scene details dict."""
        return {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": [],
            "version": None,
        }

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

    # -- View CRUD (fake) --

    def get_views(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _views for the scene."""
        return list(self._views.get(scene_id, []))

    def get_view_detail(
        self,
        base_id: str,
        scene_id: str,
        view_code: str,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Look up view by code."""
        for v in self._views.get(scene_id, []):
            if v.get("viewCode") == view_code:
                return v
        return None

    def create_view(self, base_id: str, scene_id: str, view: Any) -> Any:  # noqa: ARG002
        """Record created view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_views.append((base_id, scene_id, view))
        self._views.setdefault(scene_id, []).append(view)
        return view

    def update_view(  # noqa: ARG002
        self, base_id: str, scene_id: str, view_code: str, view: Any
    ) -> Any:
        """Record updated view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_views.append((base_id, scene_id, view_code, view))
        return view

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        """Record deleted view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_views.append((base_id, scene_id, view_code))

    # -- Relation CRUD (fake) --

    def get_relations(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _relations for the scene."""
        return list(self._relations.get(scene_id, []))

    def get_relation_detail(  # noqa: ARG002
        self, base_id: str, scene_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Look up relation by code."""
        for r in self._relations.get(scene_id, []):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, scene_id: str, rel: Any) -> Any:  # noqa: ARG002
        """Record created relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_relations.append((base_id, scene_id, rel))
        self._relations.setdefault(scene_id, []).append(rel)
        return rel

    def update_relation(  # noqa: ARG002
        self, base_id: str, scene_id: str, rel_code: str, rel: Any
    ) -> Any:
        """Record updated relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_relations.append((base_id, scene_id, rel_code, rel))
        return rel

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        """Record deleted relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_relations.append((base_id, scene_id, rel_code))

    # -- Action CRUD (fake) --

    def get_actions(  # noqa: ARG002
        self, base_id: str, scene_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Return preset _actions for the object."""
        return list(self._actions.get(object_code, []))

    def get_action_detail(  # noqa: ARG002
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Look up action by code."""
        for a in self._actions.get(object_code, []):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(  # noqa: ARG002
        self, base_id: str, scene_id: str, object_code: str, action: Any
    ) -> Any:
        """Record created action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_actions.append((base_id, scene_id, object_code, action))
        self._actions.setdefault(object_code, []).append(action)
        return action

    def update_action(  # noqa: ARG002
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Record updated action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_actions.append(
            (base_id, scene_id, object_code, action_code, action)
        )
        return action

    def delete_action(  # noqa: ARG002
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        """Record deleted action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_actions.append((base_id, scene_id, object_code, action_code))

    # -- Datasource CRUD (fake) --

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _datasources for the scene."""
        return list(self._datasources.get(scene_id, []))

    def get_datasource_detail(  # noqa: ARG002
        self, base_id: str, scene_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Look up datasource by db_id."""
        for ds in self._datasources.get(scene_id, []):
            db_list = ds.get("db", [])
            if db_list and isinstance(db_list, list) and db_list:
                if str(db_list[0].get("dbId", "")) == db_id:
                    return ds
            elif str(ds.get("dbId", ds.get("db_id", ""))) == db_id:
                return ds
        return None

    def create_datasource(self, base_id: str, scene_id: str, ds: Any) -> Any:  # noqa: ARG002
        """Record created datasource."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_datasources.append((base_id, scene_id, ds))
        self._datasources.setdefault(scene_id, []).append(ds)
        return ds

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        """Record deleted datasource."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_datasources.append((base_id, scene_id, db_id))

    # -- Scene management (fake) --

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _scenes list."""
        return list(self._scenes)

    def query_scenes(  # noqa: ARG002
        self, base_id: str, keyword: str | None
    ) -> list[dict[str, Any]]:
        """Return preset _scenes list filtered by keyword."""
        if not keyword:
            return list(self._scenes)
        kw = keyword.strip().lower()
        return [
            s
            for s in self._scenes
            if kw in s.get("sceneName", "").lower()
            or kw in s.get("sceneCode", "").lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:  # noqa: ARG002
        """Return count of matching scenes."""
        return len(self.query_scenes(base_id, keyword))

    def get_scene_details(  # noqa: ARG002
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict[str, Any]:
        """Return preset _scene_details or empty details."""
        return dict(self._scene_details.get(scene_id, self._empty_scene_details()))

    def query_ontologies_by_scene(  # noqa: ARG002
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Return preset _ontologies_by_scene or empty result."""
        result = self._ontologies_by_scene.get(scene_id, {"data": [], "totalCount": 0})
        if keyword:
            kw = keyword.strip().lower()
            data = [
                o
                for o in result.get("data", [])
                if kw in o.get("ontologyName", "").lower()
                or kw in o.get("ontologyCode", "").lower()
                or kw in o.get("ontologyDesc", "").lower()
            ]
            total = len(data)
            start = (page - 1) * page_size
            return {"data": data[start : start + page_size], "totalCount": total}
        return result


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
        self._batch_searches: list[dict[str, Any]] = []
        self._search_instances_result: dict[str, Any] = {"data": [], "totalCount": 0}
        self._graph_path_result: dict[str, Any] = {"path": [], "edges": [], "hops": -1}

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

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return preset _ontology_search_results or empty dict.

        Records the call for test inspection via ``_batch_searches``.
        """
        self._batch_searches.append(
            {
                "base_id": base_id,
                "keyword": keyword,
                "limit": limit,
                "result": dict(self._ontology_search_results),
            }
        )
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

    # -- Instance search & graph path (fake) --

    def search_instances(
        self,
        base_id: str,  # noqa: ARG002
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return preset _search_instances_result or empty."""
        return dict(self._search_instances_result)

    def graph_path(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,  # noqa: ARG002
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Return preset _graph_path_result or empty path."""
        return dict(self._graph_path_result)


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
