"""Type contracts for command plugins."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypedDict


class CommandExecutionContext(TypedDict):
    """Runtime context passed to command plugins."""

    ext_params: dict[str, Any]
    session_id: str
    workspace_dir: str | None
    gateway_context: Any | None


CommandResult = tuple[bool, dict[str, Any] | None]
CommandCallable = Callable[..., CommandResult | Awaitable[CommandResult]]


class CommandPluginProtocol(Protocol):
    """Optional protocol implemented by command plugin objects."""

    plugin_id: str
    priority: int
    enabled: bool

    def handle(self, *, context: CommandExecutionContext) -> CommandResult | Awaitable[CommandResult]:
        """Handle one ext command payload."""

