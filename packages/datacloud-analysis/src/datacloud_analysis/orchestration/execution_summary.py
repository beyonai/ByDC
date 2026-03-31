"""Execution summary model + persistence helpers for insight node."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

_LATEST_SUMMARY_FILE = "execution_summary_latest.json"
_HISTORY_SUMMARY_FILE = "execution_summary_history.jsonl"


class TodoStats(TypedDict):
    pending: int
    running: int
    done: int
    skipped: int
    failed: int
    blocked: int
    total: int


class ExecutionSummary(TypedDict, total=False):
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


class SummaryPersistResult(TypedDict, total=False):
    status: Literal["ok", "skipped", "failed"]
    latest_path: str
    history_path: str
    reason: str
    error: str


def _safe_text(value: Any) -> str:
    return str(value) if value is not None else ""


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


def build_execution_summary(
    *,
    state: dict[str, Any],
    history_content: str,
    part23: str,
    session_id: str,
) -> ExecutionSummary:
    todos = [todo for todo in (state.get("todos") or []) if isinstance(todo, dict)]
    return {
        "summary_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "agent_id": _safe_text(state.get("agent_id")),
        "query_mode": _safe_text(state.get("query_mode")),
        "user_query": _safe_text(state.get("user_query")),
        "enriched_query": _safe_text(state.get("enriched_query")),
        "intent": _safe_text(state.get("intent")),
        "execution_status": _safe_text(state.get("execution_status")),
        "result_count": len(state.get("results") or []),
        "todo_stats": _compute_todo_stats(todos),
        "todo_active_id": _safe_text(state.get("todo_active_id")),
        "artifact_refs": list(state.get("artifact_refs") or []),
        "history_chars": len(history_content),
        "part23_chars": len(part23),
        "final_answer_preview": history_content[:500],
    }


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
        return loaded
    return None
