"""Type contracts for tool hook plugins."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

HookAction = Literal["continue", "patch", "short_circuit", "interrupt", "fail", "recover"]


class HookError(TypedDict, total=False):
    """Structured tool error payload."""

    error_type: str
    message: str
    stack: str


class HookContext(TypedDict, total=False):
    """Runtime context passed to tool hook plugins."""

    session_id: str
    thread_id: str
    agent_id: str | None
    checkpoint_id: str | None
    checkpoint_ns: str | None
    todo_id: str | None
    react_step_id: str | None
    tool_name: str
    tool_params: dict[str, Any]
    user_query: str
    enriched_query: str | None
    term_context: list[dict[str, Any]]
    knowledge_snippets: list[dict[str, Any]]
    workspace_dir: str | None
    tool_output: Any
    tool_error: HookError | None
    metadata: dict[str, Any]


class HookDecision(TypedDict, total=False):
    """One hook decision returned by plugin callbacks."""

    action: HookAction
    patch: dict[str, Any]
    result: dict[str, Any]
    interrupt: dict[str, Any]
    audit: dict[str, Any]


ToolHookCallback = Callable[[HookContext], HookDecision | Awaitable[HookDecision] | None]
