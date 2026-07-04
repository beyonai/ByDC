"""OntologyLoader lazy-load cache manager — multi-base.

Replaces the file-watching runtime with a simple in-memory cache keyed by base_id.
Each base's loader is built once via DatacloudPlatform and cached until invalidated.
"""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from fastapi import Request

if TYPE_CHECKING:
    from datacloud_platform.config import Settings
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


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
    fingerprint: str | None = None
    source_files: tuple[Any, ...] = field(default_factory=tuple)
    action_routes: dict[str, ActionRouteRef] = field(default_factory=dict)
    source: str = "runtime"


class LoaderRuntimeManager:
    """Lazy-load cache manager for OntologyLoader snapshots per base_id.

    Builds loaders via :class:`DatacloudPlatform`, caches them in memory,
    and provides invalidation for use after ontology CRUD operations.
    """

    def __init__(self, *, platform: DatacloudPlatform, settings: Settings) -> None:
        self._platform = platform
        self._settings = settings
        self._cache: dict[str, LoaderSnapshot] = {}

    def get_loader(self, base_id: str) -> LoaderSnapshot:
        """Return the cached loader snapshot for *base_id*, building it on first access.

        Raises:
            KeyError: If *base_id* is not registered in the platform.
            PermissionError: If execution is disabled for the base.
        """
        if base_id in self._cache:
            return self._cache[base_id]
        loader = self._build_loader(base_id)
        self._configure_term_loader(loader)
        # 虚拟动作注入耗时日志
        import time as _time
        _t0 = _time.monotonic()
        self._platform.inject_virtual_actions(base_id, loader)
        _elapsed = (_time.monotonic() - _t0) * 1000
        logger.info(
            "inject_virtual_actions completed for base_id=%s in %.2f ms",
            base_id, _elapsed,
        )
        self._configure_runtime_services(loader)
        snapshot = LoaderSnapshot(
            loader=loader,
            version=1,
            loaded_at=datetime.now(UTC),
            action_routes=build_action_routes(loader),
        )
        self._cache[base_id] = snapshot
        logger.info("OntologyLoader cached for base_id=%s", base_id)
        return snapshot

    def invalidate(self, base_id: str) -> None:
        """Remove the cached snapshot for *base_id* so the next access rebuilds it."""
        self._cache.pop(base_id, None)
        logger.info("OntologyLoader cache invalidated for base_id=%s", base_id)

    def status(self) -> dict[str, Any]:
        """Return loader runtime status for diagnostics."""
        return {
            "cached_bases": list(self._cache.keys()),
            "cache_size": len(self._cache),
        }

    # ── internal builders ──────────────────────────────────────────────────────

    def _build_loader(self, base_id: str) -> OntologyLoader:
        """Build an OntologyLoader from the platform's ontology backend."""
        base_path = self._platform._base_path_for(base_id)
        return self._platform.load_ontology(base_id, base_path)  # type: ignore[return-value]

    def _configure_term_loader(self, loader: OntologyLoader) -> None:
        if getattr(loader._config, "term_loader", None) is not None:
            return

        from datacloud_data_sdk.ontology.term_loader import TermLoader

        loader.configure(term_loader=TermLoader.from_config({}))
        logger.info("Configured TermLoader")

    def _configure_runtime_services(self, loader: OntologyLoader) -> None:
        config = getattr(loader, "_config", None)
        from datacloud_platform.platform_file_storage import build_result_file_storage

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
            logger.warning(
                "DATACLOUD_LLM_API_KEY not set, LLM plan generation disabled"
            )
            return

        try:
            from datacloud_data_sdk.plan.query_plan_generator import (
                LangGraphPlanGenerator,
            )
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
        logger.info(
            "Configured LangGraphPlanGenerator with model=%s", self._settings.llm_model
        )

    def _configure_event_bus(self, loader: OntologyLoader) -> None:
        if getattr(loader._config, "event_bus", None) is not None:
            return

        from datacloud_data_sdk.events.bus import EventBus
        from datacloud_data_sdk.events.handlers import register_query_handlers
        from datacloud_data_sdk.events.trace_logger import EventTraceLogger
        from datacloud_data_sdk.events.tracing import TracingMiddleware

        bus = EventBus()
        tracing = TracingMiddleware(bus)
        register_query_handlers(bus, tracing=tracing)
        if self._settings.trace_enabled:
            trace_logger = EventTraceLogger(
                trace_log_path=self._settings.trace_log_path,
                enabled=True,
            )
            trace_logger.register(bus)
        loader.configure(event_bus=bus)


def build_external_snapshot(loader: OntologyLoader) -> LoaderSnapshot:
    """Build a LoaderSnapshot for a pre-existing OntologyLoader that is not
    managed by a LoaderRuntimeManager.

    This is used as a fallback when the MCP handler encounters a legacy loader
    that the runtime does not own.
    """
    return LoaderSnapshot(
        loader=loader,
        version=0,
        loaded_at=datetime.now(UTC),
        action_routes=build_action_routes(loader),
        source="external",
    )


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

    for view_id, scene in getattr(loader, "_views", {}).items():
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


async def get_request_loader_snapshot(
    request: Request,
    *,
    reason: str = "",
) -> LoaderSnapshot | None:
    """Resolve a :class:`LoaderSnapshot` from the app-state runtime for *request*.

    Returns ``None`` when the runtime is not initialized or has no cached bases.
    """
    runtime = getattr(request.app.state, "loader_runtime", None)
    if runtime is None:
        return None

    runtime = typing.cast(LoaderRuntimeManager, runtime)

    cached_bases: list[str] = runtime.status().get("cached_bases", [])
    if not cached_bases:
        # Try the platform's default base
        platform = runtime._platform
        try:
            base_id = platform._default_base_id()
        except RuntimeError:
            logger.warning("get_request_loader_snapshot: no bases registered")
            return None
        # Force-build the loader for the default base
        try:
            snapshot = runtime.get_loader(base_id)
        except Exception:
            logger.exception("get_request_loader_snapshot: failed to build loader")
            return None
        return snapshot

    # Return the first cached snapshot
    try:
        return runtime.get_loader(cached_bases[0])
    except Exception:
        logger.exception("get_request_loader_snapshot: failed to get loader")
        return None
