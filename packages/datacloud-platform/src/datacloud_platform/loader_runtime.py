"""OntologyLoader runtime manager — multi-base, scope-aware.

Builds loaders on demand via DatacloudPlatform. Supports scoped loading
by object/view codes through SceneLoaderMixin.
"""

from __future__ import annotations

import logging
import typing
from collections import OrderedDict
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


# 版本指纹涉及的实体表（object_fields 为派生表，随 objects 保存更新，不追踪）。
# 任一表 MAX(version) 变化 → 缓存失效重建。
_ENTITY_FINGERPRINT_TABLES: tuple[str, ...] = (
    "objects",
    "views",
    "actions",
    "relations",
    "datasources",
    "scenes",
    "bases",
)

# 快照缓存上限：dict + 简单 LRU 淘汰（超限弹出最久未访问）
_MAX_CACHED_SNAPSHOTS = 64


def _snapshot_cache_key(
    base_id: str,
    object_codes: list[str] | None,
    view_codes: list[str] | None,
) -> tuple[str, tuple[str, ...]]:
    """归一缓存键：base_id + 排序去重的 object/view codes 指纹。"""
    codes = tuple(sorted(set(object_codes or []))) + tuple(
        sorted(set(view_codes or []))
    )
    return (base_id, codes)


@dataclass
class _LoaderCacheEntry:
    """loader 快照缓存条目：快照 + 构建时版本指纹（供命中校验）。"""

    snapshot: LoaderSnapshot
    fingerprint: str


class LoaderRuntimeManager:
    """On-demand loader manager for OntologyLoader snapshots per base_id.

    Builds loaders via :class:`DatacloudPlatform`. Supports scoped loading
    via ``object_codes`` / ``view_codes`` parameters.

    ``get_loader`` 结果带快照缓存：命中时校验 7 张实体表版本指纹，
    任一变化 → 重建缓存；指纹查询失败 → 保守不缓存。
    """

    def __init__(self, *, platform: DatacloudPlatform, settings: Settings) -> None:
        self._platform = platform
        self._settings = settings
        self._snapshot_cache: OrderedDict[
            tuple[str, tuple[str, ...]], _LoaderCacheEntry
        ] = OrderedDict()

    def get_loader(
        self,
        base_id: str,
        *,
        object_codes: list[str] | None = None,
        view_codes: list[str] | None = None,
    ) -> LoaderSnapshot:
        """Return a loader snapshot for *base_id*, building it on demand.

        When *object_codes* or *view_codes* are provided, scoped loading via
        :meth:`SceneLoaderMixin.load_ontology_from_codes` is used instead of
        the full-ontology build path.

        快照缓存：命中缓存时校验版本指纹（7 张实体表 storage_version 拼接），
        与构建时指纹一致 → 直接返回缓存快照（含虚拟动作已注入的完整快照）；
        任一变化 → 重建。指纹查询失败 → 不信任缓存也不写缓存（保守直建）。

        Raises:
            KeyError: If *base_id* is not registered in the platform.
            PermissionError: If execution is disabled for the base.
        """
        cache_key = _snapshot_cache_key(base_id, object_codes, view_codes)
        fingerprint = self._current_fingerprint(base_id)
        entry = self._snapshot_cache.get(cache_key)
        if entry is not None and fingerprint is not None and entry.fingerprint == fingerprint:
            self._snapshot_cache.move_to_end(cache_key)
            logger.info(
                "loader snapshot cache hit: base_id=%s key=%s", base_id, cache_key
            )
            return entry.snapshot

        snapshot = self._build_snapshot(
            base_id, object_codes=object_codes, view_codes=view_codes
        )
        if fingerprint is not None:
            self._snapshot_cache[cache_key] = _LoaderCacheEntry(
                snapshot=snapshot, fingerprint=fingerprint
            )
            self._snapshot_cache.move_to_end(cache_key)
            while len(self._snapshot_cache) > _MAX_CACHED_SNAPSHOTS:
                self._snapshot_cache.popitem(last=False)
        logger.info(
            "loader snapshot built and cached: base_id=%s key=%s",
            base_id,
            cache_key,
        )
        return snapshot

    def _current_fingerprint(self, base_id: str) -> str | None:
        """版本指纹：7 张实体表 storage_version 拼接（base_id 范围）。

        任一表 MAX(version) 变化 → 指纹串变化 → 缓存失效。查询异常 → None
        （调用方保守处理：不命中缓存、不写缓存）。
        """
        try:
            backend = self._platform._ontology_for(base_id)
            store = backend._entity_store.sub_store(base_id)  # type: ignore[attr-defined]
            return "|".join(
                f"{t}:{store.storage_version(t)}" for t in _ENTITY_FINGERPRINT_TABLES
            )
        except Exception:
            logger.warning(
                "loader 版本指纹查询失败，本次不缓存快照: base_id=%s",
                base_id,
                exc_info=True,
            )
            return None

    def _build_snapshot(
        self,
        base_id: str,
        *,
        object_codes: list[str] | None = None,
        view_codes: list[str] | None = None,
    ) -> LoaderSnapshot:
        """构建 loader 快照（scoped 或全量），含虚拟动作注入与运行期服务配置。"""
        if object_codes is not None or view_codes is not None:
            loader = self._platform.load_ontology_from_codes(
                base_id,
                object_codes or [],
                view_codes=view_codes,
            )
        else:
            loader = self._build_loader(base_id)
        self._configure_term_loader(loader)
        # 虚拟动作注入耗时日志
        import time as _time

        _t0 = _time.monotonic()
        self._platform.inject_virtual_actions(base_id, loader)
        _elapsed = (_time.monotonic() - _t0) * 1000
        logger.info(
            "inject_virtual_actions completed for base_id=%s in %.2f ms",
            base_id,
            _elapsed,
        )
        self._configure_runtime_services(loader)
        snapshot = LoaderSnapshot(
            loader=loader,
            version=1,
            loaded_at=datetime.now(UTC),
            action_routes=build_action_routes(loader),
        )
        logger.info("OntologyLoader built for base_id=%s", base_id)
        return snapshot

    def status(self) -> dict[str, Any]:
        """Return loader runtime status for diagnostics."""
        entries = self._platform._base_registry.list()
        return {"bases": [e.base_id for e in entries]}

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
        loader.configure(platform=self._platform)

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

    bases: list[str] = runtime.status().get("bases", [])
    if not bases:
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

    # Return the first registered base's snapshot
    try:
        return runtime.get_loader(bases[0])
    except Exception:
        logger.exception("get_request_loader_snapshot: failed to get loader")
        return None
