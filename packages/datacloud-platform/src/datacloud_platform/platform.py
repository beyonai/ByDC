"""DatacloudPlatform — unified ontology + knowledge + execution platform entry point.

Multi-base router: injects OntologyBaseRegistry, routes every operation by base_id.
Each base independently declares its 4 Backend dimensions via source_type presets
and manual_backends overrides.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, final
from uuid import uuid4

from datacloud_platform.backends.registry import get_backend_factory
from datacloud_platform.backends.resolution import resolve_backend_names
from datacloud_platform.base_entry import _default_registry_path, generate_snowflake

if TYPE_CHECKING:
    from datacloud_platform.backends.execution import ExecutionBackend
    from datacloud_platform.backends.knowledge import KnowledgeBackend
    from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
    from datacloud_platform.backends.storage import StorageBackend
    from datacloud_platform.base_entry import OntologyBaseEntry, OntologyBaseRegistry
    from datacloud_platform.models.base_entry import OntologyBaseUpdate
    from datacloud_platform.models.shared import MatchResult, ObjectSummary

try:
    from datacloud_knowledge.ingestion.ontology_terms import build_terms as _build_terms
except ImportError:
    _build_terms = None

logger = logging.getLogger(__name__)


@final
@dataclass
class DatacloudPlatform:
    """Unified ontology + knowledge + execution + storage platform — multi-base router.

    Dependency injection:
      - _base_registry: OntologyBaseRegistry → base_id lookup
      - _backend_cache: instance cache, reuses same (type_name, impl_name) instances

    Every public method accepts base_id and internally resolves the correct Backend
    instance via 3-layer resolution: defaults → preset → manual_backends.
    """

    # ── Base registry (injected, required) ──
    _base_registry: OntologyBaseRegistry = field(init=True)
    """OntologyBaseRegistry — library management, always local."""

    # ── Backend instance cache ──
    _backend_cache: dict[str, Any] = field(default_factory=dict, init=False)

    # ── Persist path ──
    _registry_path: Path = field(default_factory=_default_registry_path, init=False)
    """Filesystem path for base registry JSON persistence."""

    # ── Config params ──
    workspace: str = field(default="")
    library_id: str = field(default="PERSONAL_LIB")
    top_k: int = field(default=20)
    enable_rerank: bool = field(default=True)

    _initialized: bool = field(default=False, init=False)

    # ── Routing core: base_id → 3-layer resolution → Backend instance ──

    def _resolve_entry(self, base_id: str) -> OntologyBaseEntry:
        """Look up an OntologyBaseEntry from the registry.

        Raises:
            KeyError: If base_id is not registered.
        """
        entry: OntologyBaseEntry | None = self._base_registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        return entry

    def _resolve_names(self, entry: OntologyBaseEntry) -> dict[str, str]:
        """3-layer resolution: defaults → preset overlay → manual override.

        Delegates to the shared resolve_backend_names function for correctness.
        """
        return resolve_backend_names(entry.source_type, entry.manual_backends)

    def _get_backend(self, type_name: str, impl_name: str) -> Any:  # noqa: ANN401
        """Get or create a Backend instance (cached).

        Cache key is ``{type_name}:{impl_name}`` — same pair reuses same instance.
        """
        cache_key = f"{type_name}:{impl_name}"
        if cache_key not in self._backend_cache:
            factory = get_backend_factory(type_name, impl_name)
            self._backend_cache[cache_key] = factory()
        return self._backend_cache[cache_key]

    def _ontology_for(self, base_id: str) -> OntologyBackend:
        """Resolve and cache the OntologyBackend for a given base_id."""
        names = self._resolve_names(self._resolve_entry(base_id))
        return self._get_backend("ontology", names["ontology"])  # type: ignore[no-any-return]

    def _knowledge_for(self, base_id: str) -> KnowledgeBackend:
        """Resolve and cache the KnowledgeBackend for a given base_id."""
        names = self._resolve_names(self._resolve_entry(base_id))
        return self._get_backend("knowledge", names["knowledge"])  # type: ignore[no-any-return]

    def _execution_for(self, base_id: str) -> ExecutionBackend | None:
        """Resolve ExecutionBackend for a given base_id.

        Returns None when the resolved name is ``"none"``.
        """
        names = self._resolve_names(self._resolve_entry(base_id))
        name = names["execution"]
        if name == "none":
            return None
        return self._get_backend("execution", name)  # type: ignore[no-any-return]

    def _storage_for(self, base_id: str) -> StorageBackend | None:
        """Resolve StorageBackend for a given base_id.

        Returns None when the resolved name is ``"none"``.
        """
        names = self._resolve_names(self._resolve_entry(base_id))
        name = names["storage"]
        if name == "none":
            return None
        return self._get_backend("storage", name)  # type: ignore[no-any-return]

    def _base_path_for(self, base_id: str) -> Path:
        """Derive the base ontology path from the entry's backend_config, with fallback."""
        entry = self._resolve_entry(base_id)
        onto_cfg = entry.backend_config.get("ontology", {})
        path_str: str = onto_cfg.get("base_path", f"/data/{base_id}")
        return Path(path_str)

    # ── Lifecycle ──

    async def initialize(self) -> None:
        """Initialize all backend connections (placeholder for future async init)."""
        if self._initialized:
            return
        self._initialized = True

    # ── Library management (always local) ──

    def list_bases(self) -> list[dict[str, Any]]:
        """List all registered ontology bases as dicts."""
        return [asdict(e) for e in self._base_registry.list()]

    def base_exists(self, base_id: str) -> bool:
        """Return True if *base_id* is registered."""
        return self._base_registry.exists(base_id)

    def create_base(self, entry: OntologyBaseEntry) -> dict[str, Any]:
        """Register a new ontology base.

        If *entry.base_id* is empty, a snowflake ID is auto-generated.

        Persists the registry to disk after registering.

        Raises:
            ValueError: If a base with the same base_id already exists.
        """
        if not entry.base_id:
            entry.base_id = generate_snowflake()
        self._base_registry.register(entry)
        self._base_registry.persist(self._registry_path)
        return asdict(entry)

    def delete_base(self, base_id: str) -> None:
        """Remove a registered ontology base.

        Persists the registry to disk after removing.

        Raises:
            KeyError: If base_id is not registered.
        """
        self._base_registry.unregister(base_id)
        self._base_registry.persist(self._registry_path)

    def update_base(self, base_id: str, updates: OntologyBaseUpdate) -> dict[str, Any]:
        """Update fields of an existing ontology base.

        *updates* is an ``OntologyBaseUpdate``; only non-None fields are applied.
        ``baseId`` is read-only and ignored.

        Returns the full updated entry as a dict.

        Raises:
            KeyError: If base_id is not registered.
        """
        fields: dict[str, Any] = updates.model_dump(exclude_none=True)
        entry = self._base_registry.update(base_id, **fields)
        self._base_registry.persist(self._registry_path)
        return asdict(entry)

    # ── Ontology: query / CRUD ──

    def load_ontology(self, base_id: str, base_path: str | Path) -> OntologyQueryable:
        """Load ontology from a base_path, returning a queryable handle."""
        return self._ontology_for(base_id).load_ontology(Path(base_path))

    def get_objects(self, base_id: str) -> list[ObjectSummary]:
        """Get all ontology object summaries under a base."""
        backend = self._ontology_for(base_id)
        loader = backend.load_ontology(self._base_path_for(base_id))
        return backend.get_objects(loader, base_id)

    def get_object_detail(self, base_id: str, object_code: str) -> ObjectSummary | None:
        """Get a single object's detail by code."""
        backend = self._ontology_for(base_id)
        loader = backend.load_ontology(self._base_path_for(base_id))
        return backend.get_object_detail(loader, object_code)

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Create an ontology object.

        REMOTE backends raise PermissionError internally — Platform does not
        check permissions.

        Side effect: if datacloud-knowledge is installed, writes term data
        so the new object can be hit by vector search.
        """
        result = self._ontology_for(base_id).create_object(base_id, obj)
        if _build_terms is not None:
            try:
                fields = [
                    {
                        "property_code": (
                            p.property_code if hasattr(p, "property_code") else str(p)
                        ),
                        "property_name": (
                            p.property_name if hasattr(p, "property_name") else str(p)
                        ),
                        "data_type": "STRING",
                    }
                    for p in (getattr(obj, "properties", None) or [])
                ]
                _build_terms(
                    entity_code=getattr(obj, "object_code", ""),
                    entity_name=str(
                        getattr(obj, "object_name", None)
                        or getattr(obj, "object_code", "")
                    ),
                    fields=fields,
                    entity_desc=getattr(obj, "object_desc", "") or "",
                )
                logger.info(
                    "create_object: build_terms done for %s",
                    getattr(obj, "object_code", "?"),
                )
            except Exception:
                logger.warning(
                    "create_object: build_terms failed for %s",
                    getattr(obj, "object_code", "?"),
                    exc_info=True,
                )
        return result

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update an ontology object.

        REMOTE backends raise PermissionError internally.
        """
        return self._ontology_for(base_id).update_object(base_id, object_code, obj)

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Delete an ontology object.

        REMOTE backends raise PermissionError internally.
        """
        self._ontology_for(base_id).delete_object(base_id, object_code)

    # ── Knowledge: search / disambiguation ──

    def search(
        self,
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

        Returns consumer-facing JSON as dict.
        """
        return self._knowledge_for(base_id).search_ontology(
            base_id,
            scene_id,
            keyword=keyword,
            query_type=query_type,
            search_scope=search_scope,
            **kwargs,
        )

    def search_ontology_batch(
        self,
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
        self,
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

    # ── Execution: Action execution ──

    async def execute_action(
        self,
        base_id: str,
        loader: Any,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an Action via the execution backend.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return await backend.execute_action(loader, object_code, action_code, arguments)

    def generate_action_tools(
        self,
        base_id: str,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate LangChain Tool descriptors for a single ontology object.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.generate_action_tools(loader, object_code)

    def generate_dynamic_query_tools(
        self,
        base_id: str,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate dynamic query tool descriptors for a single ontology object.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.generate_dynamic_query_tools(loader, object_code)

    def inject_virtual_actions(self, base_id: str, loader: Any) -> None:
        """Inject virtual Actions into a loader via execution backend.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        backend.inject_virtual_actions(loader)

    def build_filters_schema(self, base_id: str, fields: list[Any]) -> dict[str, Any]:
        """Build a JSON Schema object for virtual-action filter fields.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.build_filters_schema(fields)

    # ── Storage: file / result persistence ──

    def store_result(
        self,
        base_id: str,
        key: str,
        data: bytes,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a result file; returns file_id.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        return backend.store_result(key, data, metadata=metadata)

    def get_result(self, base_id: str, file_id: str) -> bytes:
        """Retrieve a stored result file.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        return backend.get_result(file_id)

    def delete_result(self, base_id: str, file_id: str) -> None:
        """Delete a stored result file.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        backend.delete_result(file_id)

    # ── Orchestration: cross-Backend workflows ──

    def import_owl(
        self, base_id: str, scene_id: str, zip_bytes: bytes
    ) -> dict[str, Any]:
        """Import an OWL zip: unzip → parse → write objects/views/relations → sync terms.

        Returns a summary dict: ``{"objects": N, "views": N, "relations": N}``.
        """
        import io
        import zipfile

        onto = self._ontology_for(base_id)
        know = self._knowledge_for(base_id)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            extract_dir = Path(f"/tmp/owl_import_{uuid4().hex}")
            zf.extractall(extract_dir)

        try:
            parsed = onto.parse_owl(extract_dir)
        finally:
            import shutil

            shutil.rmtree(extract_dir, ignore_errors=True)

        obj_count = 0
        for obj_dict in parsed.objects:
            try:
                onto.create_object(base_id, obj_dict)
                obj_count += 1
            except Exception as exc:
                logger.warning("Failed to create object from OWL import: %s", exc)

        # Sync terms for each object
        for obj_dict in parsed.objects:
            try:
                code: str = obj_dict.get("object_code", "")
                name: str = obj_dict.get("object_name", "")
                source: str = obj_dict.get("object_source", "")
                fields: list[dict[str, Any]] = obj_dict.get("properties", [])
                know.sync_terms(
                    code,
                    name,
                    source,
                    fields,
                    backfill_vectors=True,
                )
            except Exception as exc:
                logger.warning("Failed to sync terms for object: %s", exc)

        view_count = len(parsed.views)
        rel_count = len(parsed.relations)

        return {"objects": obj_count, "views": view_count, "relations": rel_count}

    # ── Scene: query + detail ──

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """List scene directories under a base."""
        return self._ontology_for(base_id).list_scenes(base_id)

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter."""
        return self._ontology_for(base_id).query_scenes(base_id, keyword)

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching optional keyword filter."""
        return self._ontology_for(base_id).count_scenes(base_id, keyword)

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get full scene details with optional filtering by view_code or object_code."""
        return self._ontology_for(base_id).get_scene_details(
            base_id, scene_id, view_code=view_code, object_code=object_code
        )

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Query ontologies (objects) in a scene with pagination and keyword filter."""
        return self._ontology_for(base_id).query_ontologies_by_scene(
            base_id, scene_id, page=page, page_size=page_size, keyword=keyword
        )

    # ── Scene CRUD ──

    def create_scene(self, base_id: str, scene: Any) -> Any:
        """Create a scene (grouping container)."""
        return self._ontology_for(base_id).create_scene(base_id, scene)

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> Any:
        """Update scene metadata."""
        return self._ontology_for(base_id).update_scene(base_id, scene_id, updates)

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources."""
        self._ontology_for(base_id).delete_scene(base_id, scene_id)

    # ── Scene member management ──

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Add objects/views to a scene (idempotent)."""
        return self._ontology_for(base_id).add_scene_members(
            base_id, scene_id, object_codes, view_codes
        )

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remove objects/views from a scene — does NOT delete resources."""
        return self._ontology_for(base_id).remove_scene_members(
            base_id, scene_id, object_codes, view_codes
        )

    # ── View CRUD ──

    def get_views(self, base_id: str) -> list[dict[str, Any]]:
        """Get all views under a base."""
        return self._ontology_for(base_id).get_views(base_id)

    def get_view_detail(self, base_id: str, view_code: str) -> dict[str, Any] | None:
        """Get single view detail by code."""
        return self._ontology_for(base_id).get_view_detail(base_id, view_code)

    def create_view(self, base_id: str, view: Any) -> Any:
        """Create a view. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_view(base_id, view)

    def update_view(self, base_id: str, view_code: str, view: Any) -> Any:
        """Update a view. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_view(base_id, view_code, view)

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Delete a view. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_view(base_id, view_code)

    # ── Relation CRUD ──

    def get_relations(self, base_id: str) -> list[dict[str, Any]]:
        """Get all relations under a base."""
        return self._ontology_for(base_id).get_relations(base_id)

    def get_relation_detail(self, base_id: str, rel_code: str) -> dict[str, Any] | None:
        """Get single relation detail by code."""
        return self._ontology_for(base_id).get_relation_detail(base_id, rel_code)

    def create_relation(self, base_id: str, rel: Any) -> Any:
        """Create a relation. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_relation(base_id, rel)

    def update_relation(self, base_id: str, rel_code: str, rel: Any) -> Any:
        """Update a relation. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_relation(base_id, rel_code, rel)

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Delete a relation. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_relation(base_id, rel_code)

    # ── Datasource CRUD ──

    def get_datasources(self, base_id: str) -> list[dict[str, Any]]:
        """Get all datasources under a base."""
        return self._ontology_for(base_id).get_datasources(base_id)

    def get_datasource_detail(self, base_id: str, db_id: str) -> dict[str, Any] | None:
        """Get single datasource detail by db_id."""
        return self._ontology_for(base_id).get_datasource_detail(base_id, db_id)

    def create_datasource(self, base_id: str, ds: Any) -> Any:
        """Create a datasource. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_datasource(base_id, ds)

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Delete a datasource. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_datasource(base_id, db_id)

    # ── Action CRUD ──

    def get_actions(self, base_id: str, object_code: str) -> list[dict[str, Any]]:
        """Get all actions on an object."""
        return self._ontology_for(base_id).get_actions(base_id, object_code)

    def get_action_detail(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> dict[str, Any] | None:
        """Get single action detail by code."""
        return self._ontology_for(base_id).get_action_detail(
            base_id, object_code, action_code
        )

    def create_action(self, base_id: str, object_code: str, action: Any) -> Any:
        """Create an action. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_action(base_id, object_code, action)

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Update an action. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_action(
            base_id, object_code, action_code, action
        )

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Delete an action. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_action(base_id, object_code, action_code)

    # ── Search & Graph (knowledge-backend routed) ──

    def search_instances(
        self,
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
        self,
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
        self, base_id: str, field_aliases: dict[str, list[str]]
    ) -> dict[str, list[tuple[str, str]]]:
        """Resolve field aliases to (actual_field, confidence_score) tuples."""
        return self._knowledge_for(base_id).resolve_field_aliases(field_aliases)

    def store_clarification_results(
        self, base_id: str, results: dict[str, Any], user_id: str
    ) -> list[str]:
        """Store clarification results, return stored record IDs."""
        return self._knowledge_for(base_id).store_clarification_results(
            results, user_id
        )

    def finalize_clarification(
        self,
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

    # ── Backward-compatible convenience methods (optional transition bridge) ──

    def _default_base_id(self) -> str:
        """Return the first registered base_id, for backward-compat convenience methods.

        Raises:
            RuntimeError: If no bases are registered.
        """
        entries = self._base_registry.list()
        if not entries:
            raise RuntimeError(
                "No OntologyBase registered — use create_base() first, "
                "or call methods with explicit base_id."
            )
        e: OntologyBaseEntry = entries[0]
        return e.base_id
