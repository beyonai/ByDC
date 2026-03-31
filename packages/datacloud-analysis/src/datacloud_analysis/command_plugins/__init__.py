"""Command plugins for worker-side ext command handling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "CommandPluginManager",
    "handle_ext_command",
]

if TYPE_CHECKING:
    from datacloud_analysis.command_plugins.ext_command_dispatcher import handle_ext_command
    from datacloud_analysis.command_plugins.manager import CommandPluginManager


def __getattr__(name: str) -> Any:
    """Lazily import command plugin exports to avoid eager plugin side effects."""
    if name == "CommandPluginManager":
        from datacloud_analysis.command_plugins.manager import CommandPluginManager

        return CommandPluginManager
    if name == "handle_ext_command":
        from datacloud_analysis.command_plugins.ext_command_dispatcher import handle_ext_command

        return handle_ext_command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
