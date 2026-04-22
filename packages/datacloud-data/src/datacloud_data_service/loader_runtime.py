"""OntologyLoader runtime lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.ontology.loader import OntologyLoader

if TYPE_CHECKING:
    from fastapi import Request

    from datacloud_data_service.config import Settings

logger = logging.getLogger(__name__)

WATCHED_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".owl"})
MAX_RECENT_EVENTS = 20


class ChangeKind(IntEnum):
    """watchfiles numeric event codes."""

    ADDED = 1
    MODIFIED = 2
    DELETED = 3


@dataclass(frozen=True)
class ActionRouteRef:
    """Snapshot-local action route used by MCP tools/call."""

    scope_type: str
    scope_code: str
    action_family: str | None = None


@dataclass(frozen=True)
class LoaderSnapshot:
    """Immutable view of the active loader runtime state."""

    loader: OntologyLoader
    version: int
    loaded_at: datetime
    fingerprint: str
    source_files: tuple[Path, ...] = field(default_factory=tuple)
    action_routes: dict[str, ActionRouteRef] = field(default_factory=dict)
    source: str = "runtime"


def build_external_snapshot(loader: OntologyLoader) -> LoaderSnapshot:
    """Wrap a legacy app.state.loader override as a runtime snapshot."""
    return LoaderSnapshot(
        loader=loader,
        version=0,
        loaded_at=datetime.now(UTC),
        fingerprint="external",
        source_files=(),
        action_routes=build_action_routes(loader),
        source="external",
    )


async def get_request_loader_snapshot(
    request: Request,
    *,
    reason: str,
) -> LoaderSnapshot | None:
    """Resolve the active loader snapshot for a FastAPI request.

    The runtime manager is the primary source. A direct ``app.state.loader``
    override is still honored for legacy tests and local embedding code.
    """
    runtime = _coerce_runtime(getattr(request.app.state, "loader_runtime", None))
    legacy_loader = getattr(request.app.state, "loader", None)

    if runtime is not None:
        snapshot = await runtime.ensure_fresh(reason)
        if (
            legacy_loader is not None
            and snapshot is not None
            and legacy_loader is not snapshot.loader
            and not runtime.owns_loader(legacy_loader)
        ):
            return build_external_snapshot(legacy_loader)
        return snapshot

    if legacy_loader is None:
        return None
    return build_external_snapshot(legacy_loader)


class LoaderRuntimeManager:
    """Build, publish, and refresh OntologyLoader snapshots."""

    def __init__(
        self,
        *,
        settings: Settings,
        datasource_configs: dict[str, Any] | None = None,
        loader_override: OntologyLoader | None = None,
        performance_handler_factory: Callable[[], tuple[Any, dict[str, list[Any]]]] | None = None,
        on_publish: Callable[[LoaderSnapshot], None] | None = None,
    ) -> None:
        self._settings = settings
        self._datasource_configs = datasource_configs
        self._loader_override = loader_override
        self._performance_handler_factory = performance_handler_factory
        self._on_publish = on_publish
        self._snapshot: LoaderSnapshot | None = None
        self._reload_lock = asyncio.Lock()
        self._dirty = False
        self._version = 0
        self._watch_task: asyncio.Task[None] | None = None
        self._last_reload_error: str | None = None
        self._last_reload_reason = ""
        self._managed_loader_ids: set[int] = set()
        self._last_reload_at: datetime | None = None
        self._recent_watch_events: list[dict[str, str]] = []

    @property
    def current_loader(self) -> OntologyLoader | None:
        """Return the current loader if initialized."""
        return self._snapshot.loader if self._snapshot is not None else None

    def owns_loader(self, loader: Any) -> bool:
        """Return whether the loader was published by this runtime."""
        return id(loader) in self._managed_loader_ids

    async def start(self) -> None:
        """Load the initial snapshot and optionally start file watching."""
        await self.reload(force=True, reason="startup")
        if self._should_watch():
            self._watch_task = asyncio.create_task(
                self._watch_loop(),
                name="datacloud-loader-watch",
            )

    async def stop(self) -> None:
        """Stop background watcher tasks."""
        if self._watch_task is None:
            return
        self._watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._watch_task
        self._watch_task = None

    async def get_snapshot(self) -> LoaderSnapshot | None:
        """Return the current snapshot without freshness checks."""
        return self._snapshot

    async def ensure_fresh(self, reason: str) -> LoaderSnapshot | None:
        """Refresh the loader if files changed, then return the active snapshot."""
        if self._snapshot is None:
            return await self.reload(force=True, reason=reason)

        if not getattr(self._settings, "loader_reload_enabled", True):
            return self._snapshot

        current_fingerprint, _ = self._compute_fingerprint()
        if self._dirty or current_fingerprint != self._snapshot.fingerprint:
            return await self.reload(reason=reason)

        return self._snapshot

    async def reload(
        self,
        *,
        force: bool = False,
        reason: str = "",
    ) -> LoaderSnapshot | None:
        """Build a fresh loader snapshot and publish it atomically on success."""
        async with self._reload_lock:
            if self._snapshot is not None and not force:
                fingerprint, _ = self._compute_fingerprint()
                if not self._dirty and fingerprint == self._snapshot.fingerprint:
                    return self._snapshot

            try:
                loader = self._build_loader()
                fingerprint, source_files = self._compute_fingerprint()
                self._version += 1
                snapshot = LoaderSnapshot(
                    loader=loader,
                    version=self._version,
                    loaded_at=datetime.now(UTC),
                    fingerprint=fingerprint,
                    source_files=source_files,
                    action_routes=build_action_routes(loader),
                )
            except Exception as exc:
                self._last_reload_error = str(exc)
                logger.exception("OntologyLoader reload failed, keeping previous snapshot")
                if force and self._snapshot is None:
                    raise
                return self._snapshot

            self._snapshot = snapshot
            self._managed_loader_ids.add(id(loader))
            self._dirty = False
            self._last_reload_error = None
            self._last_reload_reason = reason
            self._last_reload_at = snapshot.loaded_at
            if self._on_publish is not None:
                self._on_publish(snapshot)
            logger.info(
                "OntologyLoader snapshot published version=%s reason=%s files=%s",
                snapshot.version,
                reason,
                len(snapshot.source_files),
            )
            return snapshot

    def mark_dirty(self, reason: str) -> None:
        """Mark the current snapshot stale."""
        self._dirty = True
        self._last_reload_reason = reason

    def status(self) -> dict[str, Any]:
        """Return loader runtime status for diagnostics."""
        snapshot = self._snapshot
        ontology_path = Path(self._settings.ontology_path).resolve()
        watched_paths = [str(path) for path in self._watch_paths()]
        return {
            "initialized": snapshot is not None,
            "version": snapshot.version if snapshot else 0,
            "loaded_at": snapshot.loaded_at.isoformat() if snapshot else "",
            "source": snapshot.source if snapshot else "",
            "ontology_path": str(ontology_path),
            "watched_paths": watched_paths,
            "source_file_count": len(snapshot.source_files) if snapshot else 0,
            "dirty": self._dirty,
            "last_reload_at": self._last_reload_at.isoformat() if self._last_reload_at else "",
            "last_reload_reason": self._last_reload_reason,
            "last_reload_error": self._last_reload_error,
            "watch_enabled": self._should_watch(),
            "recent_watch_events": list(self._recent_watch_events),
        }

    def _build_loader(self) -> OntologyLoader:
        loader = OntologyLoader()
        self._inherit_loader_config(loader)
        self._configure_term_loader(loader)

        self._load_ontology(loader)
        self._configure_runtime_services(loader)
        self._configure_datasources(loader)

        from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

        inject_virtual_actions(loader)
        logger.info("Injected virtual actions for DB/KB objects")
        return loader

    def _inherit_loader_config(self, loader: OntologyLoader) -> None:
        """Carry forward runtime config from the previous loader snapshot.

        Datasource and KB source configs are intentionally excluded so the new
        ontology load can rebuild them from source files and explicit overrides.
        """
        if self._loader_override is not None:
            previous_loader = self._loader_override
        else:
            snapshot = self._snapshot
            if snapshot is None:
                return
            previous_loader = snapshot.loader
        previous_config = getattr(previous_loader, "_config", None)
        current_config = getattr(loader, "_config", None)
        if previous_config is None or current_config is None:
            return

        inherited: dict[str, Any] = {}
        for config_field in fields(current_config):
            if config_field.name in {"datasource_configs", "kb_source_configs"}:
                continue
            inherited[config_field.name] = getattr(previous_config, config_field.name)

        if inherited:
            loader.configure(**inherited)

    def _configure_term_loader(self, loader: OntologyLoader) -> None:
        if getattr(loader._config, "term_loader", None) is not None:
            return

        from datacloud_data_sdk.ontology.term_loader import TermLoader

        loader.configure(term_loader=TermLoader.from_config({}))
        logger.info("Configured TermLoader")

    def _load_ontology(self, loader: OntologyLoader) -> None:
        ontology_path = Path(self._settings.ontology_path)
        if not ontology_path.exists():
            logger.warning("Ontology path does not exist: %s", ontology_path)
            return

        if ontology_path.is_dir() and (ontology_path / "ontology").exists():
            loader.load_from_owl_directory(ontology_path)
        elif ontology_path.is_dir() and (
            (ontology_path / "object").exists() or (ontology_path / "view").exists()
        ):
            loader.load_from_owl_resource_directory(ontology_path)
        else:
            loader.load_from_path(ontology_path)
        logger.info("Loaded ontology from %s", ontology_path)

    def _configure_runtime_services(self, loader: OntologyLoader) -> None:
        config = getattr(loader, "_config", None)
        from datacloud_data_service.file_storage import build_result_file_storage

        result_file_storage = build_result_file_storage(self._settings)
        if config is not None and config.result_file_storage:
            result_file_storage = config.result_file_storage
        loader.configure(result_file_storage=result_file_storage)
        self._configure_plan_generator(loader)
        self._configure_event_bus(loader)
        loader.configure(csv_base_dir=self._settings.csv_base_dir)
        loader.configure(sql_execution_mode=self._settings.sql_execution_mode)
        loader.configure(
            query_result_csv_threshold=self._settings.query_result_csv_threshold,
        )

    def _configure_plan_generator(self, loader: OntologyLoader) -> None:
        if getattr(loader._config, "plan_generator", None) is not None:
            return

        if not self._settings.llm_api_key:
            logger.warning("DATACLOUD_LLM_API_KEY not set, LLM plan generation disabled")
            return

        try:
            from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator
        except ImportError as exc:
            logger.warning(
                "langchain-openai not installed, LLM plan generation disabled: %s",
                exc,
                exc_info=True,
            )
            return

        plan_gen = LangGraphPlanGenerator(
            model=self._settings.llm_model,
            base_url=self._settings.llm_api_base,
            api_key=self._settings.llm_api_key,
            temperature=self._settings.llm_temperature,
            max_retries=self._settings.max_plan_retries,
        )
        loader.configure(plan_generator=plan_gen)
        logger.info("Configured LangGraphPlanGenerator with model=%s", self._settings.llm_model)

    def _configure_event_bus(self, loader: OntologyLoader) -> None:
        if getattr(loader._config, "event_bus", None) is not None:
            return

        from datacloud_data_sdk.events.bus import EventBus
        from datacloud_data_sdk.events.handlers import register_query_handlers
        from datacloud_data_sdk.events.trace_logger import EventTraceLogger
        from datacloud_data_sdk.events.tracing import TracingMiddleware

        bus = EventBus()
        tracing = TracingMiddleware(bus)
        if self._performance_handler_factory is not None:
            perf_handler, _ = self._performance_handler_factory()
            tracing.on_span_complete(perf_handler)
        register_query_handlers(bus, tracing=tracing)
        if self._settings.trace_enabled:
            trace_logger = EventTraceLogger(
                trace_log_path=self._settings.trace_log_path,
                enabled=True,
            )
            trace_logger.register(bus)
        loader.configure(event_bus=bus)

    def _configure_datasources(self, loader: OntologyLoader) -> None:
        if self._datasource_configs is not None:
            loader.configure(datasource_configs=self._datasource_configs)

    def _should_watch(self) -> bool:
        return bool(getattr(self._settings, "loader_watch_enabled", False))

    async def _watch_loop(self) -> None:
        try:
            from watchfiles import awatch
        except ImportError:
            logger.warning("watchfiles not installed, loader file watching disabled")
            return

        watch_paths = self._watch_paths()
        if not watch_paths:
            logger.warning("No ontology watch paths found, loader file watching disabled")
            return

        debounce_seconds = (
            max(
                getattr(self._settings, "loader_reload_debounce_ms", 500),
                0,
            )
            / 1000
        )
        async for _changes in awatch(*watch_paths):
            self._record_watch_events(_changes)
            logger.info(
                "OntologyLoader watcher detected %d change(s): %s",
                len(_changes),
                ", ".join(f"{_change_kind_name(change)}:{path}" for change, path in _changes),
            )
            self.mark_dirty("file_watch")
            if debounce_seconds:
                await asyncio.sleep(debounce_seconds)
            await self.reload(reason="file_watch")

    def _watch_paths(self) -> tuple[Path, ...]:
        ontology_path = Path(self._settings.ontology_path)
        if ontology_path.is_file():
            return (ontology_path.parent,)
        if ontology_path.is_dir():
            target_paths: list[Path] = []
            for relative_dir in (
                Path("ontology/objects"),
                Path("ontology/views"),
                Path("object"),
                Path("view"),
            ):
                candidate = ontology_path / relative_dir
                if candidate.is_dir():
                    target_paths.append(candidate)
            if target_paths:
                return tuple(target_paths)
            return (ontology_path,)
        return ()

    def _compute_fingerprint(self) -> tuple[str, tuple[Path, ...]]:
        files = tuple(_iter_source_files(Path(self._settings.ontology_path)))
        hasher = hashlib.sha256()
        for file_path in files:
            try:
                stat = file_path.stat()
            except FileNotFoundError:
                continue
            hasher.update(str(file_path).encode("utf-8"))
            hasher.update(str(stat.st_mtime_ns).encode("ascii"))
            hasher.update(str(stat.st_size).encode("ascii"))
        return hasher.hexdigest(), files

    def _record_watch_events(self, changes: Iterable[tuple[Any, str]]) -> None:
        timestamp = datetime.now(UTC).isoformat()
        for change, path in changes:
            self._recent_watch_events.append(
                {
                    "at": timestamp,
                    "kind": _change_kind_name(int(change)),
                    "path": path,
                }
            )
        if len(self._recent_watch_events) > MAX_RECENT_EVENTS:
            self._recent_watch_events = self._recent_watch_events[-MAX_RECENT_EVENTS:]


def build_action_routes(loader: OntologyLoader) -> dict[str, ActionRouteRef]:
    """Build a snapshot-local action route index."""
    routes: dict[str, ActionRouteRef] = {}
    for cls in loader.get_ontology_classes():
        for action in cls.actions:
            scope_type = getattr(action, "scope_type", None) or "object"
            scope_code = getattr(action, "scope_code", None) or cls.object_code
            routes[action.action_code] = ActionRouteRef(
                scope_type=scope_type,
                scope_code=scope_code,
                action_family=getattr(action, "action_family", None),
            )
            for alias in getattr(action, "legacy_aliases", []) or []:
                routes.setdefault(
                    alias,
                    ActionRouteRef(
                        scope_type=scope_type,
                        scope_code=scope_code,
                        action_family=getattr(action, "action_family", None),
                    ),
                )

    for view_id, scene in getattr(loader, "_scenes", {}).items():
        for action in scene.get("_virtual_actions", []):
            action_code = getattr(action, "action_code", "")
            if not action_code:
                continue
            routes[action_code] = ActionRouteRef(
                scope_type="view",
                scope_code=view_id,
                action_family=getattr(action, "action_family", None),
            )
    return routes


def _iter_source_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path.resolve()]
    if not path.is_dir():
        return []

    result: list[Path] = []
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        if item.suffix.lower() in WATCHED_SUFFIXES or item.name == "manifest.json":
            result.append(item.resolve())
    return sorted(result)


def _coerce_runtime(value: Any) -> LoaderRuntimeManager | None:
    if isinstance(value, LoaderRuntimeManager):
        return value
    return None


def _change_kind_name(change: int) -> str:
    try:
        return ChangeKind(change).name.lower()
    except ValueError:
        return f"unknown({change})"
