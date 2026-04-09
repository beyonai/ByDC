"""Command plugin manager (builtin + extension)."""

from __future__ import annotations

import importlib.util
import logging
import os
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from datacloud_analysis.command_plugins.ext_command_dispatcher import ExtCommandDispatcherPlugin
from datacloud_analysis.command_plugins.types import (
    CommandCallable,
    CommandExecutionContext,
    CommandResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LoadedCommandPlugin:
    plugin_id: str
    priority: int
    handler: CommandCallable
    source: str


def _awaitable(value: Any) -> bool:
    return hasattr(value, "__await__")


async def _invoke_handler(
    handler: CommandCallable, context: CommandExecutionContext
) -> CommandResult:
    try:
        result = handler(
            ext_params=context["ext_params"],
            session_id=context["session_id"],
            workspace_dir=context["workspace_dir"],
            gateway_context=context["gateway_context"],
        )
    except TypeError:
        result = handler(
            ext_params=context["ext_params"],
            session_id=context["session_id"],
            workspace_dir=context["workspace_dir"],
        )
    if _awaitable(result):
        return cast(CommandResult, await cast(Awaitable[Any], result))
    return cast(CommandResult, result)


class CommandPluginManager:
    """Runtime command plugin manager."""

    def __init__(self, plugins: list[_LoadedCommandPlugin]) -> None:
        self._plugins = sorted(plugins, key=lambda p: (p.priority, p.plugin_id))

    @classmethod
    def from_defaults(cls) -> CommandPluginManager:
        """Build manager from builtin and extension command plugins."""
        plugins: list[_LoadedCommandPlugin] = []

        builtin = ExtCommandDispatcherPlugin()
        if builtin.enabled:

            def _builtin_handler(
                *,
                ext_params: dict[str, Any],
                session_id: str,
                workspace_dir: str | None,
                gateway_context: Any = None,
            ) -> CommandResult:
                _ = gateway_context
                context: CommandExecutionContext = {
                    "ext_params": ext_params,
                    "session_id": session_id,
                    "workspace_dir": workspace_dir,
                    "gateway_context": None,
                }
                return builtin.handle(context=context)

            plugins.append(
                _LoadedCommandPlugin(
                    plugin_id=builtin.plugin_id,
                    priority=builtin.priority,
                    handler=_builtin_handler,
                    source="builtin",
                )
            )

        plugins.extend(_load_extension_plugins())
        return cls(plugins)

    async def handle_ext_command(
        self,
        *,
        ext_params: dict[str, Any],
        session_id: str,
        workspace_dir: str | None,
        gateway_context: Any = None,
    ) -> CommandResult:
        """Run command plugins in priority order and return first handled result."""
        context: CommandExecutionContext = {
            "ext_params": ext_params,
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "gateway_context": gateway_context,
        }
        for plugin in self._plugins:
            try:
                handled, payload = await _invoke_handler(plugin.handler, context)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Command plugin failed: plugin_id=%s source=%s error=%s",
                    plugin.plugin_id,
                    plugin.source,
                    exc,
                )
                continue
            if handled:
                logger.info(
                    "Command plugin handled ext command: plugin_id=%s source=%s command=%s",
                    plugin.plugin_id,
                    plugin.source,
                    ext_params.get("command"),
                )
                return True, payload
        return False, None


def _load_extension_plugins() -> list[_LoadedCommandPlugin]:
    plugins: list[_LoadedCommandPlugin] = []
    for plugin_file in _iter_extension_plugin_files():
        loaded = _load_one_extension_plugin(plugin_file)
        if loaded is not None:
            plugins.append(loaded)
    return plugins


def _iter_extension_plugin_files() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in _candidate_command_plugin_dirs():
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("__"):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    return found


def _candidate_command_plugin_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_raw = os.getenv("DATACLOUD_COMMAND_PLUGIN_DIRS", "").strip()
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
            / "command_plugins"
        )
    return dirs


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        marker = (
            parent / "examples" / "e_commerce_demo" / "backend" / "datacloud_service" / "plugins"
        )
        if marker.exists():
            return parent
    return None


def _load_one_extension_plugin(path: Path) -> _LoadedCommandPlugin | None:
    module_name = f"datacloud_analysis_ext_command_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        loader = spec.loader
        loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to import command plugin file=%s error=%s", path, exc)
        return None

    plugin_obj: Any
    if hasattr(module, "register"):
        try:
            plugin_obj = module.register()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Command plugin register() failed file=%s error=%s", path, exc)
            return None
    elif hasattr(module, "handle_ext_command"):
        plugin_obj = module.handle_ext_command
    else:
        logger.warning("Command plugin ignored (missing register/handle_ext_command): %s", path)
        return None

    enabled = bool(getattr(plugin_obj, "enabled", getattr(module, "ENABLED", True)))
    if not enabled:
        return None

    priority = int(getattr(plugin_obj, "priority", getattr(module, "PRIORITY", 500)))
    plugin_id = (
        str(getattr(plugin_obj, "plugin_id", getattr(module, "PLUGIN_ID", path.stem))).strip()
        or path.stem
    )
    handler = _resolve_handler(plugin_obj)
    if handler is None:
        logger.warning("Command plugin ignored (no callable handler): %s", path)
        return None
    return _LoadedCommandPlugin(
        plugin_id=plugin_id,
        priority=priority,
        handler=handler,
        source=str(path),
    )


def _resolve_handler(plugin_obj: Any) -> CommandCallable | None:
    if callable(plugin_obj):
        return cast(CommandCallable, plugin_obj)
    handle = getattr(plugin_obj, "handle", None)
    if callable(handle):

        def _wrapped_handle(
            *,
            ext_params: dict[str, Any],
            session_id: str,
            workspace_dir: str | None,
            gateway_context: Any = None,
        ) -> CommandResult | Awaitable[CommandResult]:
            context: CommandExecutionContext = {
                "ext_params": ext_params,
                "session_id": session_id,
                "workspace_dir": workspace_dir,
                "gateway_context": gateway_context,
            }
            return cast(CommandResult | Awaitable[CommandResult], handle(context=context))

        return _wrapped_handle
    handle_ext = getattr(plugin_obj, "handle_ext_command", None)
    if callable(handle_ext):
        return cast(CommandCallable, handle_ext)
    return None
