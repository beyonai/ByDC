"""Type contracts for tool hook plugins."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict


class HookSignalError(Exception):
    """Base class for exceptions that must propagate through the hook manager.

    Subclass this when a hook callback needs to signal a control-flow change
    (e.g. clarification required) that must not be swallowed by the manager's
    generic exception handler.
    """


class ClarificationNeededError(HookSignalError):
    """澄清插件检测到需要用户确认时抛出，替代直接调用 interrupt()。

    定义在 types.py（静态模块）以确保动态加载的插件与静态导入使用同一类对象，
    避免 isinstance 检查因模块双重加载而失败。
    """

    def __init__(self, context: dict[str, Any]) -> None:
        super().__init__("clarification required")
        self.context = context


HookAction = Literal[
    "continue", "patch", "short_circuit", "interrupt", "fail", "recover", "redirect"
]


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
    term_hints: list[dict[str, Any]]
    term_context: list[dict[str, Any]]
    knowledge_snippets: list[dict[str, Any]]
    knowledge_payload: dict[str, Any]
    workspace_dir: str | None
    tool_output: Any
    tool_error: HookError | None
    metadata: dict[str, Any]


class HookPatch(TypedDict, total=False):
    """Patch payload for context mutation."""

    tool_params: dict[str, Any]
    knowledge_snippets_append: list[dict[str, Any]]
    term_context_append: list[dict[str, Any]]


class HookResult(TypedDict, total=False):
    """Terminal result payload for short_circuit/fail/recover."""

    tool_output: Any
    tool_error: HookError


class HookInterrupt(TypedDict, total=False):
    """Interrupt payload schema for human-in-the-loop."""

    reason_code: str
    prompt: str
    required_fields: list[str]
    resume_payload_schema: dict[str, Any]


class HookAudit(TypedDict, total=False):
    """Audit payload for plugin decision logs."""

    plugin_id: str
    message: str
    risk_level: Literal["low", "medium", "high"]


class HookDecision(TypedDict, total=False):
    """One hook decision returned by plugin callbacks."""

    action: HookAction
    tool: str  # redirect 目标工具名，如 data_query_ads_enterprise_analysis
    params: dict[str, Any]  # redirect 时透传给目标工具的参数
    patch: HookPatch
    result: HookResult
    interrupt: HookInterrupt
    audit: HookAudit

    # Legacy schema fields (kept for compatibility)
    tool_params: dict[str, Any]
    knowledge_snippets_append: list[dict[str, Any]]
    term_context_append: list[dict[str, Any]]
    short_circuit: bool
    block: bool
    recover: bool
    output: Any
    error: str | HookError


class SkillCallAudit(TypedDict, total=False):
    """Structured audit record for skill invocation."""

    event: Literal["skill_call_audit"]
    task_id: str
    skill_name: str
    trigger_tool: str
    risk_level: Literal["low", "medium", "high"]
    allowlist_tags: list[str]
    blocklist_tags: list[str]
    status: str
    elapsed_ms: int
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]
    checkpoint_id: str | None
    checkpoint_ns: str | None
    error: str


ToolHookCallback = Callable[[HookContext], HookDecision | Awaitable[HookDecision] | None]
