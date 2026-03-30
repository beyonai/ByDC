"""Execution node for the 5-node main pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.agent_delegate import agent_delegate_node
from datacloud_analysis.orchestration.clarification import clarification_node
from datacloud_analysis.orchestration.direct_tool import direct_tool_node
from datacloud_analysis.orchestration.loop import loop_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _todo_md_with_status(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "# TODOs\n\n- (empty)\n"
    lines = ["# TODOs", ""]
    for todo in todos:
        lines.append(
            f"- [{todo.get('status', 'pending')}] {todo.get('todo_id', '')}: {todo.get('goal', '')}"
        )
    lines.append("")
    return "\n".join(lines)


def _sync_todos_from_plan(
    *,
    todos: list[dict[str, Any]],
    plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not todos:
        return []
    status_by_id = {str(task.get("id")): str(task.get("status", "pending")) for task in plan}
    synced: list[dict[str, Any]] = []
    for todo in todos:
        todo_id = str(todo.get("todo_id", ""))
        next_status = status_by_id.get(todo_id, str(todo.get("status", "pending")))
        synced.append({**todo, "status": next_status})
    return synced


def _pick_active_todo(todos: list[dict[str, Any]]) -> dict[str, Any] | None:
    for todo in todos:
        if str(todo.get("status", "pending")) == "pending":
            return todo
    return todos[0] if todos else None


def _compute_effective_tools(todo: dict[str, Any]) -> list[str]:
    required_capabilities = [
        str(x) for x in (todo.get("required_capabilities") or []) if str(x).strip()
    ]
    required_tools = [str(x) for x in (todo.get("required_tools") or []) if str(x).strip()]
    required = required_capabilities if required_capabilities else required_tools

    blocked = {
        str(x)
        for x in ((todo.get("blocked_capabilities") or []) + (todo.get("blocked_tools") or []))
        if str(x).strip()
    }
    if not required:
        return []
    return [tool for tool in required if tool not in blocked]


def _persist_todo_md(
    *,
    workspace_dir: str | None,
    todo_md: str | None,
    existing_path: str | None,
) -> str | None:
    if not todo_md:
        return existing_path

    target: Path | None = None
    if existing_path:
        target = Path(existing_path)
    elif workspace_dir:
        target = Path(workspace_dir) / "temp" / "todo.md"
    if target is None:
        return existing_path

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(todo_md, encoding="utf-8")
        return str(target)
    except OSError as exc:
        logger.warning("execution_node: failed to persist todo.md: %s", exc)
        return existing_path


def _build_invocation_id(
    *,
    query_mode: str,
    target_tool: str,
    tool_params: dict[str, Any] | None,
    todo_active_id: str,
) -> str:
    payload = json.dumps(
        {
            "query_mode": query_mode,
            "target_tool": target_tool,
            "tool_params": tool_params or {},
            "todo_active_id": todo_active_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _append_trace(
    trace: list[dict[str, Any]],
    *,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    next_trace = list(trace)
    entry: dict[str, Any] = {"stage": stage, "status": status}
    if detail:
        entry["detail"] = detail
    next_trace.append(entry)
    return next_trace


async def execution_node(
    state: AgentState,
    config: RunnableConfig,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute current plan/direct route and decide next step."""
    gateway_context = (config.get("configurable") or {}).get("gateway_context")
    todos = list(state.get("todos") or [])
    active_todo = _pick_active_todo(todos)
    effective_tools = _compute_effective_tools(active_todo) if active_todo else []
    todo_active_id = str(active_todo.get("todo_id", "")) if active_todo else ""
    existing_todo_md_path = (
        str(state.get("todo_md_path")) if state.get("todo_md_path") else None
    )
    invocation_dedup = [str(x) for x in (state.get("invocation_dedup") or []) if str(x).strip()]
    invocation_dedup_set = set(invocation_dedup)
    execution_trace = list(state.get("execution_trace") or [])

    has_required = bool(
        active_todo
        and (
            list(active_todo.get("required_capabilities") or [])
            or list(active_todo.get("required_tools") or [])
        )
    )
    if has_required and not effective_tools and active_todo is not None:
        blocked_todos: list[dict[str, Any]] = []
        active_id = todo_active_id
        for todo in todos:
            if str(todo.get("todo_id", "")) == active_id:
                blocked_todos.append({**todo, "status": "blocked"})
            else:
                blocked_todos.append(todo)
        blocked_todo_md = _todo_md_with_status(blocked_todos)
        todo_md_path = _persist_todo_md(
            workspace_dir=state.get("workspace_dir"),
            todo_md=blocked_todo_md,
            existing_path=existing_todo_md_path,
        )
        return {
            "todos": blocked_todos,
            "todo_active_id": active_id,
            "active_tools": [],
            "execution_status": "replan",
            "todo_md": blocked_todo_md,
            "todo_md_path": todo_md_path,
            "execution_trace": _append_trace(
                execution_trace,
                stage="execution",
                status="replan",
                detail={"reason": "no_effective_tools", "todo_id": active_id},
            ),
            "invocation_dedup": invocation_dedup,
        }

    if state.get("ambiguous_terms"):
        updates = await clarification_node(state, gateway_context=gateway_context)
        if updates.get("ambiguous_terms"):
            return {
                **updates,
                "todo_active_id": todo_active_id,
                "active_tools": effective_tools,
                "execution_status": "done",
                "execution_trace": _append_trace(
                    execution_trace,
                    stage="clarification",
                    status="waiting",
                    detail={"todo_id": todo_active_id},
                ),
                "invocation_dedup": invocation_dedup,
            }
        return {
            **updates,
            "todo_active_id": todo_active_id,
            "active_tools": effective_tools,
            "execution_status": "replan",
            "execution_trace": _append_trace(
                execution_trace,
                stage="clarification",
                status="resolved",
                detail={"todo_id": todo_active_id},
            ),
            "invocation_dedup": invocation_dedup,
        }

    query_mode = str(state.get("query_mode") or "analysis")
    if query_mode == "chitchat" or bool(state.get("clarify_needed")):
        return {
            "todo_active_id": todo_active_id,
            "active_tools": effective_tools,
            "execution_status": "done",
            "execution_trace": _append_trace(
                execution_trace,
                stage="execution",
                status="done",
                detail={"query_mode": query_mode},
            ),
            "invocation_dedup": invocation_dedup,
        }

    if query_mode == "agent_delegate":
        invocation_id = _build_invocation_id(
            query_mode=query_mode,
            target_tool=str(state.get("target_tool") or ""),
            tool_params=state.get("tool_params"),
            todo_active_id=todo_active_id,
        )
        if invocation_id in invocation_dedup_set:
            done_todos = [{**t, "status": "done"} for t in todos] if todos else []
            dedup_online_todo_md: str | None = _todo_md_with_status(done_todos) if done_todos else None
            todo_md_path = _persist_todo_md(
                workspace_dir=state.get("workspace_dir"),
                todo_md=dedup_online_todo_md,
                existing_path=existing_todo_md_path,
            )
            return {
                "todo_active_id": todo_active_id,
                "active_tools": effective_tools,
                "execution_status": "done",
                "todos": done_todos if done_todos else todos,
                "todo_md": dedup_online_todo_md,
                "todo_md_path": todo_md_path,
                "execution_trace": _append_trace(
                    execution_trace,
                    stage="agent_delegate",
                    status="dedup_skipped",
                    detail={"invocation_id": invocation_id},
                ),
                "invocation_dedup": invocation_dedup,
            }
        delegated = await agent_delegate_node(state, config, default_tools=default_tools)
        invocation_dedup.append(invocation_id)
        done_todos = [{**t, "status": "done"} for t in todos] if todos else []
        delegated_todo_md: str | None = _todo_md_with_status(done_todos) if done_todos else None
        todo_md_path = _persist_todo_md(
            workspace_dir=state.get("workspace_dir"),
            todo_md=delegated_todo_md,
            existing_path=existing_todo_md_path,
        )
        return {
            **delegated,
            "todo_active_id": todo_active_id,
            "active_tools": effective_tools,
            "execution_status": "done",
            "todos": done_todos if done_todos else todos,
            "todo_md": delegated_todo_md,
            "todo_md_path": todo_md_path,
            "execution_trace": _append_trace(
                execution_trace,
                stage="agent_delegate",
                status="done",
                detail={"invocation_id": invocation_id},
            ),
            "invocation_dedup": invocation_dedup,
        }

    if query_mode == "online_query":
        invocation_id = _build_invocation_id(
            query_mode=query_mode,
            target_tool=str(state.get("target_tool") or ""),
            tool_params=state.get("tool_params"),
            todo_active_id=todo_active_id,
        )
        if invocation_id in invocation_dedup_set:
            done_todos = [{**t, "status": "done"} for t in todos] if todos else []
            dedup_todo_md: str | None = _todo_md_with_status(done_todos) if done_todos else None
            todo_md_path = _persist_todo_md(
                workspace_dir=state.get("workspace_dir"),
                todo_md=dedup_todo_md,
                existing_path=existing_todo_md_path,
            )
            return {
                "todo_active_id": todo_active_id,
                "active_tools": effective_tools,
                "execution_status": "done",
                "todos": done_todos if done_todos else todos,
                "todo_md": dedup_todo_md,
                "todo_md_path": todo_md_path,
                "execution_trace": _append_trace(
                    execution_trace,
                    stage="direct_tool",
                    status="dedup_skipped",
                    detail={"invocation_id": invocation_id},
                ),
                "invocation_dedup": invocation_dedup,
            }
        direct = await direct_tool_node(state, gateway_context=gateway_context, default_tools=default_tools)
        invocation_dedup.append(invocation_id)
        done_todos = [{**t, "status": "done"} for t in todos] if todos else []
        direct_todo_md: str | None = _todo_md_with_status(done_todos) if done_todos else None
        todo_md_path = _persist_todo_md(
            workspace_dir=state.get("workspace_dir"),
            todo_md=direct_todo_md,
            existing_path=existing_todo_md_path,
        )
        return {
            **direct,
            "todo_active_id": todo_active_id,
            "active_tools": effective_tools,
            "execution_status": "done",
            "todos": done_todos if done_todos else todos,
            "todo_md": direct_todo_md,
            "todo_md_path": todo_md_path,
            "execution_trace": _append_trace(
                execution_trace,
                stage="direct_tool",
                status="done",
                detail={"invocation_id": invocation_id},
            ),
            "invocation_dedup": invocation_dedup,
        }

    # analysis path: run one loop round then continue until no pending tasks
    loop_updates = await loop_node(state, gateway_context=gateway_context, default_tools=default_tools)
    for invocation_id in (loop_updates.get("invocation_dedup_add") or []):
        invocation_id_text = str(invocation_id).strip()
        if invocation_id_text and invocation_id_text not in invocation_dedup_set:
            invocation_dedup.append(invocation_id_text)
            invocation_dedup_set.add(invocation_id_text)
    updated_plan = list(loop_updates.get("plan") or state.get("plan") or [])
    synced_todos = _sync_todos_from_plan(todos=todos, plan=updated_plan)
    has_pending = any(str(task.get("status", "pending")) == "pending" for task in updated_plan)
    todos_for_md = synced_todos if synced_todos else todos
    todo_md = _todo_md_with_status(todos_for_md)
    todo_md_path = _persist_todo_md(
        workspace_dir=state.get("workspace_dir"),
        todo_md=todo_md,
        existing_path=existing_todo_md_path,
    )
    return {
        **loop_updates,
        "todos": todos_for_md,
        "todo_active_id": todo_active_id,
        "active_tools": effective_tools,
        "todo_md": todo_md,
        "todo_md_path": todo_md_path,
        "execution_status": "execution" if has_pending else "done",
        "execution_trace": _append_trace(
            execution_trace,
            stage="loop",
            status="pending" if has_pending else "done",
            detail={"todo_id": todo_active_id},
        ),
        "invocation_dedup": invocation_dedup,
    }
