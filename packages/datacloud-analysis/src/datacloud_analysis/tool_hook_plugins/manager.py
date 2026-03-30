"""Tool hook plugin manager (builtin + extension)."""

from __future__ import annotations

import importlib.util
import logging
import os
from collections.abc import Awaitable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from datacloud_analysis.tool_hook_plugins.types import HookContext, HookDecision, ToolHookCallback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LoadedToolHookPlugin:
    plugin_id: str
    priority: int
    enabled: bool
    tool_allowlist: tuple[str, ...]
    tool_blocklist: tuple[str, ...]
    before_call_back: ToolHookCallback | None
    after_call_back: ToolHookCallback | None
    source: str


def _awaitable(value: Any) -> bool:
    return hasattr(value, "__await__")


async def _invoke_callback(
    callback: ToolHookCallback,
    context: HookContext,
) -> HookDecision | None:
    result = callback(context)
    if _awaitable(result):
        return cast(HookDecision | None, await cast(Awaitable[Any], result))
    return cast(HookDecision | None, result)


def _strict_mode() -> bool:
    raw = str(os.getenv("DATACLOUD_TOOL_PLUGIN_STRICT", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


class ToolHookPluginManager:
    """Runtime manager for tool hook plugins."""

    def __init__(self, plugins: list[_LoadedToolHookPlugin]) -> None:
        self._plugins = sorted(plugins, key=lambda p: (p.priority, p.plugin_id))

    @classmethod
    def from_defaults(cls) -> ToolHookPluginManager:
        """Build manager from builtin and extension hook plugins."""
        plugins = _load_builtin_plugins() + _load_extension_plugins()
        return cls(plugins)

    async def run_before(self, context: HookContext) -> tuple[HookContext, HookDecision | None]:
        """Run before callbacks in priority ascending order."""
        ctx = cast(HookContext, dict(context))
        for plugin in self._iter_matched_plugins(str(ctx.get("tool_name") or ""), reverse=False):
            callback = plugin.before_call_back
            if callback is None:
                continue
            decision = await self._run_one_callback(
                callback=callback,
                plugin_id=plugin.plugin_id,
                context=ctx,
            )
            if decision is None:
                continue
            action = str(decision.get("action") or "continue")
            if action == "patch":
                _apply_patch(ctx, decision.get("patch"))
                continue
            if action in {"short_circuit", "interrupt", "fail"}:
                return ctx, decision
        return ctx, None

    async def run_after(self, context: HookContext) -> tuple[HookContext, HookDecision | None]:
        """Run after callbacks in priority descending order."""
        ctx = cast(HookContext, dict(context))
        terminal: HookDecision | None = None
        for plugin in self._iter_matched_plugins(str(ctx.get("tool_name") or ""), reverse=True):
            callback = plugin.after_call_back
            if callback is None:
                continue
            decision = await self._run_one_callback(
                callback=callback,
                plugin_id=plugin.plugin_id,
                context=ctx,
            )
            if decision is None:
                continue
            action = str(decision.get("action") or "continue")
            if action == "patch":
                _apply_patch(ctx, decision.get("patch"))
                continue
            if action in {"recover", "fail"}:
                terminal = decision
        return ctx, terminal

    async def _run_one_callback(
        self,
        *,
        callback: ToolHookCallback,
        plugin_id: str,
        context: HookContext,
    ) -> HookDecision | None:
        try:
            return await _invoke_callback(callback, context)
        except Exception as exc:  # noqa: BLE001
            if _strict_mode():
                logger.error("Tool hook callback failed in strict mode: plugin_id=%s error=%s", plugin_id, exc)
                return {
                    "action": "fail",
                    "result": {"tool_error": {"error_type": type(exc).__name__, "message": str(exc)}},
                    "audit": {"plugin_id": plugin_id, "message": "strict mode callback exception"},
                }
            logger.warning("Tool hook callback failed, ignored: plugin_id=%s error=%s", plugin_id, exc)
            return None

    def _iter_matched_plugins(
        self, tool_name: str, *, reverse: bool
    ) -> list[_LoadedToolHookPlugin]:
        plugins = list(reversed(self._plugins)) if reverse else list(self._plugins)
        matched: list[_LoadedToolHookPlugin] = []
        for plugin in plugins:
            if not plugin.enabled:
                continue
            if plugin.tool_allowlist and tool_name not in plugin.tool_allowlist:
                continue
            if plugin.tool_blocklist and tool_name in plugin.tool_blocklist:
                continue
            matched.append(plugin)
        return matched


def _apply_patch(context: HookContext, patch: Any) -> None:
    if not isinstance(patch, dict):
        return
    tool_params = patch.get("tool_params")
    if isinstance(tool_params, dict):
        current = context.get("tool_params")
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update(tool_params)
        context["tool_params"] = merged
    append_knowledge = patch.get("knowledge_snippets_append")
    if isinstance(append_knowledge, list):
        current_knowledge = list(context.get("knowledge_snippets") or [])
        current_knowledge.extend(item for item in append_knowledge if isinstance(item, dict))
        context["knowledge_snippets"] = current_knowledge
    append_terms = patch.get("term_context_append")
    if isinstance(append_terms, list):
        current_terms = list(context.get("term_context") or [])
        current_terms.extend(item for item in append_terms if isinstance(item, dict))
        context["term_context"] = current_terms


def _load_builtin_plugins() -> list[_LoadedToolHookPlugin]:
    return _load_plugins_from_dir(Path(__file__).resolve().parent / "builtin", source_prefix="builtin")


def _load_extension_plugins() -> list[_LoadedToolHookPlugin]:
    plugins: list[_LoadedToolHookPlugin] = []
    for directory in _candidate_extension_dirs():
        plugins.extend(_load_plugins_from_dir(directory, source_prefix="extension"))
    return plugins


def _candidate_extension_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_raw = os.getenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", "").strip()
    if env_raw:
        dirs.extend(Path(item.strip()) for item in env_raw.split(os.pathsep) if item.strip())

    repo_root = _find_repo_root()
    if repo_root is not None:
        dirs.append(
            repo_root
            / "examples"
            / "e_commerce_demo"
            / "backend"
            / "datacloud_service"
            / "plugins"
            / "tool_plugins"
        )
    return dirs


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        marker = parent / "examples" / "e_commerce_demo" / "backend" / "datacloud_service" / "plugins"
        if marker.exists():
            return parent
    return None


def _load_plugins_from_dir(directory: Path, *, source_prefix: str) -> list[_LoadedToolHookPlugin]:
    plugins: list[_LoadedToolHookPlugin] = []
    if not directory.exists() or not directory.is_dir():
        return plugins

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("__"):
            continue
        loaded = _load_one_plugin(path, source_prefix=source_prefix)
        if loaded is not None:
            plugins.append(loaded)
    return plugins


def _load_one_plugin(path: Path, *, source_prefix: str) -> _LoadedToolHookPlugin | None:
    module_name = f"datacloud_analysis_tool_hook_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        loader = spec.loader
        loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to import tool hook plugin file=%s error=%s", path, exc)
        return None

    plugin_obj: Any
    if hasattr(module, "register"):
        try:
            plugin_obj = module.register()
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool hook plugin register() failed file=%s error=%s", path, exc)
            return None
    else:
        plugin_obj = module

    plugin_id = str(
        getattr(plugin_obj, "plugin_id", getattr(module, "PLUGIN_ID", path.stem))
    ).strip() or path.stem
    priority = int(getattr(plugin_obj, "priority", getattr(module, "PRIORITY", 500)))
    enabled = bool(getattr(plugin_obj, "enabled", getattr(module, "ENABLED", True)))
    allowlist = tuple(
        str(item)
        for item in (getattr(plugin_obj, "tool_allowlist", getattr(module, "TOOL_ALLOWLIST", ())) or ())
    )
    blocklist = tuple(
        str(item)
        for item in (getattr(plugin_obj, "tool_blocklist", getattr(module, "TOOL_BLOCKLIST", ())) or ())
    )
    before = getattr(plugin_obj, "before_call_back", None)
    after = getattr(plugin_obj, "after_call_back", None)
    if before is None and after is None:
        return None
    if before is not None and not callable(before):
        before = None
    if after is not None and not callable(after):
        after = None

    return _LoadedToolHookPlugin(
        plugin_id=plugin_id,
        priority=priority,
        enabled=enabled,
        tool_allowlist=allowlist,
        tool_blocklist=blocklist,
        before_call_back=cast(ToolHookCallback | None, before),
        after_call_back=cast(ToolHookCallback | None, after),
        source=f"{source_prefix}:{path}",
    )


@lru_cache(maxsize=1)
def get_tool_hook_plugin_manager() -> ToolHookPluginManager:
    """Return a process-level cached tool hook manager."""
    return ToolHookPluginManager.from_defaults()
