"""Execution summary model + persistence helpers for insight node."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

_LATEST_SUMMARY_FILE = "execution_summary_latest.json"
_HISTORY_SUMMARY_FILE = "execution_summary_history.jsonl"
_SUMMARY_MODEL_VERSION = "v1"


class TodoStats(TypedDict):
    pending: int
    running: int
    done: int
    skipped: int
    failed: int
    blocked: int
    total: int


class ExecutionSummaryTodo(TypedDict, total=False):
    """Compact todo-level summary for persistence and replay."""

    todo_id: str
    goal: str
    status: str
    depends_on: list[str]
    required_tools: list[str]
    required_capabilities: list[str]
    last_capability: str
    error: str


class ExecutionSummary(TypedDict, total=False):
    # Legacy fields
    summary_version: str
    created_at: str
    session_id: str
    agent_id: str
    query_mode: str
    user_query: str
    enriched_query: str
    intent: str
    execution_status: str
    result_count: int
    todo_stats: TodoStats
    todo_active_id: str
    artifact_refs: list[dict[str, Any]]
    history_chars: int
    part23_chars: int
    final_answer_preview: str

    # G16 model fields
    model_version: str
    generated_at: str
    thread_id: str
    todo_total: int
    todo_done: int
    todo_failed: int
    todo_skipped: int
    todo_blocked: int
    result_total: int
    todos: list[ExecutionSummaryTodo]
    final_answer_chars: int
    extensions: dict[str, Any]


class SummaryPersistResult(TypedDict, total=False):
    status: Literal["ok", "skipped", "failed"]
    latest_path: str
    history_path: str
    reason: str
    error: str


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _compute_todo_stats(todos: list[dict[str, Any]]) -> TodoStats:
    stats: TodoStats = {
        "pending": 0,
        "running": 0,
        "done": 0,
        "skipped": 0,
        "failed": 0,
        "blocked": 0,
        "total": len(todos),
    }
    for todo in todos:
        status = str(todo.get("status", "pending")).strip().lower()
        if status in stats:
            stats[status] += 1
    return stats


def _todo_summary(todo: dict[str, Any]) -> ExecutionSummaryTodo:
    raw_caps = todo.get("required_capabilities") or []
    required_caps: list[str] = []
    if isinstance(raw_caps, list):
        for item in raw_caps:
            if isinstance(item, dict):
                cap = _safe_text(item.get("capability_id")).strip()
                if cap:
                    required_caps.append(cap)
            else:
                cap = _safe_text(item).strip()
                if cap:
                    required_caps.append(cap)

    raw_required_tools = todo.get("required_tools") or []
    required_tools = [_safe_text(item) for item in raw_required_tools if _safe_text(item).strip()]
    depends_on = [_safe_text(item) for item in (todo.get("depends_on") or []) if _safe_text(item).strip()]

    summary: ExecutionSummaryTodo = {
        "todo_id": _safe_text(todo.get("todo_id")),
        "goal": _safe_text(todo.get("goal")),
        "status": _safe_text(todo.get("status")),
        "depends_on": depends_on,
        "required_tools": required_tools,
        "required_capabilities": required_caps,
    }
    last_capability = _safe_text(todo.get("last_capability")).strip()
    if last_capability:
        summary["last_capability"] = last_capability
    error = _safe_text(todo.get("error")).strip()
    if error:
        summary["error"] = error
    return summary


def build_execution_summary(
    state: dict[str, Any],
    *,
    history_content: str = "",
    part23: str = "",
    session_id: str = "",
    gateway_context: Any = None,
    final_answer: str = "",
) -> ExecutionSummary:
    """Build a summary compatible with legacy and G16 model contracts."""
    todos = [todo for todo in (state.get("todos") or []) if isinstance(todo, dict)]
    artifact_refs = [item for item in (state.get("artifact_refs") or []) if isinstance(item, dict)]

    now = datetime.now(UTC).isoformat()

    context_session = _safe_text(getattr(gateway_context, "session_id", "")).strip()
    resolved_session_id = (session_id or context_session).strip()
    resume_context = state.get("resume_context")
    resume = resume_context if isinstance(resume_context, dict) else {}
    thread_id = _safe_text(resume.get("thread_id") or resolved_session_id).strip()

    status_values = [_safe_text(todo.get("status")).lower() for todo in todos]
    todo_total = len(todos)
    todo_done = sum(1 for status in status_values if status == "done")
    todo_failed = sum(1 for status in status_values if status == "failed")
    todo_skipped = sum(1 for status in status_values if status == "skipped")
    todo_blocked = sum(1 for status in status_values if status == "blocked")

    raw_results = state.get("results") or []
    result_total = len(raw_results) if isinstance(raw_results, list) else 0

    resolved_history = history_content or final_answer

    return {
        # Legacy fields
        "summary_version": "1.0",
        "created_at": now,
        "session_id": resolved_session_id,
        "agent_id": _safe_text(state.get("agent_id")),
        "query_mode": _safe_text(state.get("query_mode")),
        "user_query": _safe_text(state.get("user_query")),
        "enriched_query": _safe_text(state.get("enriched_query")),
        "intent": _safe_text(state.get("intent")),
        "execution_status": _safe_text(state.get("execution_status")),
        "result_count": result_total,
        "todo_stats": _compute_todo_stats(todos),
        "todo_active_id": _safe_text(state.get("todo_active_id")),
        "artifact_refs": artifact_refs,
        "history_chars": len(resolved_history),
        "part23_chars": len(part23),
        "final_answer_preview": resolved_history[:500],
        # G16 model fields
        "model_version": _SUMMARY_MODEL_VERSION,
        "generated_at": now,
        "thread_id": thread_id,
        "todo_total": todo_total,
        "todo_done": todo_done,
        "todo_failed": todo_failed,
        "todo_skipped": todo_skipped,
        "todo_blocked": todo_blocked,
        "result_total": result_total,
        "todos": [_todo_summary(todo) for todo in todos],
        "final_answer_chars": len(final_answer),
        "extensions": {},
    }


def execution_summary_to_json(summary: ExecutionSummary) -> str:
    """Serialize summary to deterministic JSON for storage and tests."""
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)


def execution_summary_from_json(payload: str) -> ExecutionSummary:
    """Deserialize summary JSON payload."""
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("execution summary payload must decode to object")
    return cast(ExecutionSummary, decoded)


def _resolve_session_dir(
    *,
    workspace_dir: str | None,
    session_id: str,
    workspace_root: str | None,
) -> Path | None:
    if workspace_root and session_id:
        return Path(workspace_root) / session_id

    if not workspace_dir:
        return None

    ws = Path(workspace_dir)
    parts = [p for p in ws.parts if p]
    if session_id and session_id in parts:
        session_index = parts.index(session_id)
        return Path(*parts[: session_index + 1])

    if ws.parent.name in {"private", "public"}:
        return ws.parent.parent
    return ws


def persist_execution_summary(
    *,
    summary: ExecutionSummary,
    workspace_dir: str | None,
    session_id: str,
    workspace_root: str | None = None,
) -> SummaryPersistResult:
    session_dir = _resolve_session_dir(
        workspace_dir=workspace_dir,
        session_id=session_id,
        workspace_root=workspace_root,
    )
    if session_dir is None:
        return {"status": "skipped", "reason": "session_dir_unresolved"}

    latest_path = session_dir / _LATEST_SUMMARY_FILE
    history_path = session_dir / _HISTORY_SUMMARY_FILE
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with history_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(summary, ensure_ascii=False))
            fp.write("\n")
        return {
            "status": "ok",
            "latest_path": str(latest_path),
            "history_path": str(history_path),
        }
    except OSError as exc:
        return {"status": "failed", "error": str(exc)}


def load_latest_summary_by_session(
    *,
    session_id: str,
    workspace_root: str | None = None,
    workspace_dir: str | None = None,
) -> ExecutionSummary | None:
    session_dir = _resolve_session_dir(
        workspace_dir=workspace_dir,
        session_id=session_id,
        workspace_root=workspace_root,
    )
    if session_dir is None:
        return None
    latest_path = session_dir / _LATEST_SUMMARY_FILE
    if not latest_path.exists():
        return None
    try:
        loaded = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(loaded, dict):
        return cast(ExecutionSummary, loaded)
    return None
