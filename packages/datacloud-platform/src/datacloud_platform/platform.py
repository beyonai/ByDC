"""DatacloudPlatform — unified ontology + term + execution + storage platform entry point.

Multi-base router: injects OntologyBaseRegistry, routes every operation by base_id.
Each base independently declares its 4 Backend dimensions via source_type presets
and manual_backends overrides.

Method implementations live in domain-specific Mixins under ``mixins/``.
This module provides the dataclass shell + routing core + lifecycle.
"""

from __future__ import annotations

import logging
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, final

from datacloud_platform.backends._contracts import (
    _HasBasePath,
    _HasExecutionBackend,
    _HasOntologyBackend,
    _HasStorageBackend,
    _HasTermBackend,
)
from datacloud_platform.backends.registry import get_backend_factory
from datacloud_platform.backends.resolution import resolve_backend_names
from datacloud_platform.backends.term import TermBackend
from datacloud_platform.mixins import (
    ActionCRUDMixin,
    DatasourceMixin,
    ExecutionMixin,
    KnowledgeMixin,
    LibraryMixin,
    OntologyBuildMixin,
    OntologyCRUDMixin,
    OntologyQueryMixin,
    OntologyWorkspaceMixin,
    OrchestrationMixin,
    RelationMixin,
    SceneLoaderMixin,
    SceneMixin,
    SceneServiceMixin,
    StorageMixin,
    TermMixin,
    ViewMixin,
    WorkspaceActionMixin,
)
from datacloud_platform.adapters.byclaw_sync import ByClawSyncAdapter
from datacloud_platform.ontology_store import OntologyStore

if TYPE_CHECKING:
    from datacloud_platform.backends.execution import ExecutionBackend
    from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
    from datacloud_platform.backends.storage import StorageBackend
    from datacloud_platform.backends.term import TermBackend
    from datacloud_platform.base_entry import OntologyBaseEntry, OntologyBaseRegistry

logger = logging.getLogger(__name__)


@final
@dataclass
class DatacloudPlatform(
    _HasOntologyBackend,
    _HasExecutionBackend,
    _HasStorageBackend,
    _HasTermBackend,
    _HasBasePath,
    LibraryMixin,
    OntologyBuildMixin,
    OntologyWorkspaceMixin,
    WorkspaceActionMixin,
    OntologyQueryMixin,
    OntologyCRUDMixin,
    SceneMixin,
    ViewMixin,
    RelationMixin,
    DatasourceMixin,
    ActionCRUDMixin,
    KnowledgeMixin,
    TermMixin,
    ExecutionMixin,
    StorageMixin,
    OrchestrationMixin,
    SceneLoaderMixin,
    SceneServiceMixin,
):
    """Unified ontology + term + execution + storage platform — multi-base router.

    Dependency injection:
      - _base_registry: OntologyBaseRegistry → base_id lookup
      - _backend_cache: instance cache, reuses same (type_name, impl_name) instances

    Every public method accepts base_id and internally resolves the correct Backend
    instance via 3-layer resolution: defaults → preset → manual_backends.
    """

    # ── Base registry (injected, required) ──
    _base_registry: OntologyBaseRegistry = field(init=True)
    """OntologyBaseRegistry — library management, always local."""

    # ── Entity store (injected, optional) ──
    _entity_store: Any = field(default=None, init=True)
    """EntityStore for OntologyStore-backed index caching."""

    # ── Ontology store (built from entity_store) ──
    _ontology_store: OntologyStore | None = field(default=None, init=True)
    """OntologyStore — in-memory index cache, built from _entity_store."""

    # ── Sync adapter (CRUD hook for ByClaw resource table) ──
    _sync_adapter: Any = field(default=None, init=False)
    """ByClawSyncAdapter — CRUD hook for syncing resources to ByClaw resource table."""

    # ── Backend instance cache ──
    _backend_cache: dict[str, Any] = field(default_factory=dict, init=False)

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
        entry = self._resolve_entry(base_id)
        names = self._resolve_names(entry)
        backend = self._get_backend("ontology", names["ontology"])
        _configure_if_supported(backend, entry)
        # Inject sync hook if available
        if self._sync_adapter is not None:
            backend._sync_hook = self._sync_adapter
        return backend  # type: ignore[no-any-return]

    def _term_for(self, base_id: str) -> TermBackend:
        """Resolve and cache the TermBackend for a given base_id."""
        entry = self._resolve_entry(base_id)
        names = self._resolve_names(entry)
        backend = self._get_backend("term", names["term"])
        _configure_if_supported(backend, entry)
        return backend  # type: ignore[no-any-return]

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
        path_str: str = onto_cfg.get("base_path", "")
        if path_str:
            return Path(path_str)
        from datacloud_platform.platform_file_storage import _data_dir

        return _data_dir() / base_id

    def __post_init__(self) -> None:
        """Build OntologyStore from entity_store if provided.

        Only primes the cache for platform-level entity types (bases, scenes).
        Domain ontology data (objects/views/relations/etc.) lives under
        per-base paths separate from the platform entity store.
        """
        if self._entity_store is not None:
            self._ontology_store = OntologyStore(self._entity_store)
            for et in ("bases", "scenes"):
                self._ontology_store.get_index(et)

        # Initialize ByClaw sync adapter (if discovery is available)
        try:
            self._sync_adapter = ByClawSyncAdapter()
            logger.info("ByClawSyncAdapter initialized")
        except Exception:
            logger.warning(
                "ByClawSyncAdapter initialization failed — sync disabled", exc_info=True
            )
            self._sync_adapter = None

    def create_base(self, entry: Any) -> dict[str, Any]:  # noqa: ANN401
        """Register a new ontology base, then ensure default scene exists.

        Overrides LibraryMixin.create_base to also trigger
        ``_ensure_default_scene``, which on first call absorbs any
        pre-existing OWL orphans (e.g. from ``_seed_from_owl_path``).

        Read-only backends (REMOTE) raise ``PermissionError`` on scene
        creation — we skip the default-scene step gracefully.
        """
        result = LibraryMixin.create_base(self, entry)
        base_id: str = result["base_id"]

        # Ensure default scene exists (absorbs any pre-existing orphans on first call)
        try:
            self._ensure_default_scene(base_id)
        except PermissionError:
            logger.info(
                "Skipping _ensure_default_scene for read-only base_id=%s", base_id
            )
        except Exception:
            logger.warning(
                "_ensure_default_scene failed for base_id=%s", base_id, exc_info=True
            )

        # Auto-seed from OWL path if configured in backend_config
        _owl_path: str = ""
        if isinstance(entry, dict):
            _owl_path = (
                entry.get("backend_config", {}).get("ontology", {}).get("owl_path", "")
            )
        elif hasattr(entry, "backend_config") and entry.backend_config:
            _owl_path = (entry.backend_config.get("ontology") or {}).get("owl_path", "")

        if _owl_path:
            try:
                self._seed_from_owl_path(base_id, _owl_path)
            except (PermissionError, AttributeError):
                logger.info("Skipping _seed_from_owl_path for base_id=%s", base_id)

        return result

    def _load_ontology_cached(
        self,
        base_id: str,
        **_kwargs: Any,
    ) -> OntologyQueryable:
        """Get an OntologyQueryable, internal helper.

        Only used by :class:`ExecutionMixin` (``generate_action_tools``,
        ``inject_virtual_actions``) and Tier-3 methods.

        For remote backends whose ``load_ontology`` raises ``PermissionError``,
        returns a stub queryable — the remote backend ignores the loader and
        fetches data via HTTP directly.
        """
        try:
            return self._ontology_for(base_id).load_ontology(
                self._base_path_for(base_id), base_id=base_id
            )
        except PermissionError:
            # Remote backends don't support load_ontology — return a stub the
            # backend will ignore (it fetches via HTTP directly).
            return types.SimpleNamespace(
                _classes={},
                _relations=[],
                _views=None,
            )

    # ── Lifecycle ──

    async def initialize(self) -> None:
        """Initialize all backend connections (placeholder for future async init)."""
        if self._initialized:
            return
        self._initialized = True

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


def _configure_if_supported(backend: Any, entry: OntologyBaseEntry) -> None:
    """Call backend.configure() if supported, passing per-base source_url and auth_config.

    Backends created by zero-arg factories don't know about the base entry.
    If a backend exposes a ``configure(source_url, auth_config)`` method,
    this function calls it to inject the per-base configuration from the entry.

    Idempotent: configure() implementations should be callable multiple times.
    """
    if not hasattr(backend, "configure"):
        return
    source_url = getattr(entry, "source_url", "") or ""
    auth_config = getattr(entry, "auth_config", None)
    backend.configure(source_url, auth_config)
