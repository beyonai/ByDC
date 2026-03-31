"""Execution node for the 5-node main pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, cast

import anyio
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from datacloud_analysis.orchestration.execution.react_runtime import select_react_capability
from datacloud_analysis.orchestration.execution.sandbox_executor import (
    ToolRuntime,
    normalize_workspace_task_output,
)
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

_TODO_DONE_STATES: frozenset[str] = frozenset({"done", "skipped"})
_BUILTIN_EXECUTOR_CAPABILITIES: frozenset[str] = frozenset(
    {
        "code_exec",
        "file_read",
        "file_write",
        "workspace-file-read",
        "workspace-file-write",
        "workspace-file-upload",
        "task-note-tool",
        "chat-response-tool",
        "recall_memory",
        "build_skill",
        "render_report",
    }
)
_DEFAULT_CAPABILITY_FALLBACK_ORDER: tuple[str, ...] = (
    "chat-response-tool",
    "workspace-file-read",
    "workspace-file-write",
    "workspace-file-upload",
    "task-note-tool",
    "file_read",
    "file_write",
    "render_report",
)
_DEFAULT_REACT_MAX_ROUNDS = 6
_DEFAULT_LEVEL3_FAILURE_THRESHOLD = 2
_LEVEL3_CONFIRM_TEXTS = {"继续", "continue", "yes", "y", "ok", "确认", "重规划"}
_LEVEL3_CANCEL_TEXTS = {"取消", "cancel", "no", "n", "停止"}
_ACTION_KEYWORDS: tuple[str, ...] = ("action", "exec", "update", "write", "operate")
_QUERY_KEYWORDS: tuple[str, ...] = ("query", "read", "search", "list", "select", "view")
_RELATION_KEYWORDS: tuple[str, ...] = ("relation", "graph", "link", "edge")


def _clarification_prompt_from_ambiguous(ambiguous_terms: list[dict[str, Any]]) -> str:
    if not ambiguous_terms:
        return "请补充术语含义。"
    first = ambiguous_terms[0] if isinstance(ambiguous_terms[0], dict) else {}
    mention = str(first.get("mention") or first.get("term") or "").strip()
    candidates_raw = first.get("candidates")
    candidates: list[str] = []
    if isinstance(candidates_raw, list):
        for item in candidates_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("term_name") or item.get("name") or "").strip()
            if text:
                candidates.append(text)
    if mention and candidates:
        return (
            f"「{mention}」存在歧义，候选有：{', '.join(candidates[:5])}。"
            "请补充具体含义，或回车跳过。"
        )
    if mention:
        return f"「{mention}」未找到匹配术语，请补充具体含义，或回车跳过。"
    return "存在未确认术语，请补充具体含义，或回车跳过。"


def _parse_clarification_resume(resume_value: Any) -> str:
    if isinstance(resume_value, dict):
        return str(
            resume_value.get("content")
            or resume_value.get("answer")
            or resume_value.get("value")
            or resume_value.get("text")
            or ""
        ).strip()
    return str(resume_value or "").strip()


async def _handle_ambiguous_terms(
    state: AgentState,
    *,
    todo_active_id: str,
    pending_capability: str,
) -> dict[str, Any]:
    ambiguous_terms = list(state.get("ambiguous_terms") or [])
    if not ambiguous_terms:
        return {
            "ambiguous_terms": [],
            "confirmed_terms": list(state.get("confirmed_terms") or []),
            "clarify_needed": False,
        }

    prompt = _clarification_prompt_from_ambiguous(ambiguous_terms)
    resume_value = interrupt(
        {
            "reason_code": "TERM_CLARIFICATION",
            "prompt": prompt,
            "required_fields": ["content"],
            "resume_payload_schema": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
            "todo_active_id": todo_active_id,
            "react_step_id": todo_active_id,
            "pending_capability": pending_capability,
            "interrupt_reason": "term_clarification",
        }
    )

    clarified = _parse_clarification_resume(resume_value)
    current = ambiguous_terms[0] if isinstance(ambiguous_terms[0], dict) else {}
    remaining = ambiguous_terms[1:]
    confirmed_terms = list(state.get("confirmed_terms") or [])
    mention = str(current.get("mention") or current.get("term") or clarified).strip()

    if clarified:
        confirmed_terms.append(
            {
                "mention": mention,
                "term_name": clarified,
                "term_id": str(current.get("term_id") or ""),
                "confidence": 1.0,
                "source": "user_clarification",
            }
        )

    return {
        "ambiguous_terms": remaining,
        "confirmed_terms": confirmed_terms,
        "clarify_needed": bool(remaining),
    }


def _todo_md_with_status(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "# TODOs\n\n- (empty)\n"
    lines = ["# TODOs", ""]
    for todo in todos:
        lines.append(
            f"- [{todo.get('status', 'pending')}] {todo.get('todo_id', '')}: {todo.get('goal', '')}"
        )
        lines.append(f"  required_tools: {todo.get('required_tools', [])}")
        lines.append(f"  blocked_tools: {todo.get('blocked_tools', [])}")
        lines.append(f"  depends_on: {todo.get('depends_on', [])}")
    lines.append("")
    return "\n".join(lines)


def _get_react_max_rounds(state: AgentState) -> int:
    raw: Any = state.get("react_max_rounds")
    if raw is None:
        raw = os.getenv("DATACLOUD_REACT_MAX_ROUNDS", str(_DEFAULT_REACT_MAX_ROUNDS))
    if not isinstance(raw, (int, float, str)):
        return _DEFAULT_REACT_MAX_ROUNDS
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_REACT_MAX_ROUNDS
    return max(1, parsed)


def _level3_failure_threshold(state: AgentState) -> int:
    raw: Any = state.get("level3_failure_threshold")
    if raw is None:
        raw = os.getenv("DATACLOUD_LEVEL3_FAILURE_THRESHOLD", str(_DEFAULT_LEVEL3_FAILURE_THRESHOLD))
    if not isinstance(raw, (int, float, str)):
        return _DEFAULT_LEVEL3_FAILURE_THRESHOLD
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LEVEL3_FAILURE_THRESHOLD
    return max(1, parsed)


def _should_trigger_level3(state: AgentState, todos: list[dict[str, Any]]) -> bool:
    threshold = _level3_failure_threshold(state)
    failed_count = sum(1 for todo in todos if str(todo.get("status", "")) == "failed")
    has_done = any(str(todo.get("status", "")) == "done" for todo in todos)
    return failed_count >= threshold and not has_done


def _parse_level3_confirmation(resume_value: Any) -> bool:
    if isinstance(resume_value, dict):
        raw = str(
            resume_value.get("confirm")
            or resume_value.get("action")
            or resume_value.get("value")
            or ""
        ).strip().lower()
    else:
        raw = str(resume_value or "").strip().lower()
    if not raw:
        return False
    if raw in _LEVEL3_CONFIRM_TEXTS:
        return True
    if raw in _LEVEL3_CANCEL_TEXTS:
        return False
    return False


def _is_overall_unreachable(
    todos: list[dict[str, Any]],
    *,
    dependency_deadlock: bool = False,
) -> bool:
    if dependency_deadlock:
        return True
    has_done = any(str(todo.get("status", "")) == "done" for todo in todos)
    has_pending = any(str(todo.get("status", "")) == "pending" for todo in todos)
    has_failed = any(str(todo.get("status", "")) == "failed" for todo in todos)
    return has_failed and not has_pending and not has_done


def _has_dependency_deadlock(todos: list[dict[str, Any]]) -> bool:
    done_ids = {
        str(todo.get("todo_id", ""))
        for todo in todos
        if str(todo.get("status", "pending")) in _TODO_DONE_STATES
    }
    pending_todos = [todo for todo in todos if str(todo.get("status", "pending")) == "pending"]
    if not pending_todos:
        return False
    ready = 0
    for todo in pending_todos:
        deps = [str(dep) for dep in (todo.get("depends_on") or [])]
        if all(dep in done_ids for dep in deps):
            ready += 1
    return ready == 0


def _build_level3_interrupt_payload(
    *,
    todo_active_id: str,
    pending_capability: str,
    interrupt_reason: str,
) -> dict[str, Any]:
    return {
        "reason_code": "LEVEL3_GLOBAL_REPLAN_CONFIRM",
        "prompt": "当前任务连续失败或不可达，是否进行整体重规划？回复“继续”或“取消”。",
        "required_fields": ["confirm"],
        "resume_payload_schema": {
            "type": "object",
            "properties": {"confirm": {"type": "string"}},
            "required": ["confirm"],
        },
        "todo_id": todo_active_id,
        "todo_active_id": todo_active_id,
        "react_step_id": todo_active_id,
        "pending_capability": pending_capability,
        "interrupt_reason": interrupt_reason,
    }


def _build_level3_result(
    *,
    confirmed: bool,
    state: AgentState,
    config: RunnableConfig,
    todos: list[dict[str, Any]],
    results: list[dict[str, Any]],
    todo_md: str,
    todo_md_path: str | None,
    todo_active_id: str,
    active_tools: list[str],
    pending_capability: str,
    execution_trace: list[dict[str, Any]],
    invocation_dedup: list[str],
) -> dict[str, Any]:
    if confirmed:
        execution_trace = _append_trace(
            execution_trace,
            stage="level3_replan",
            status="confirmed",
            detail={"decision": "replan"},
        )
        return {
            "plan": _todo_plan_from_todos(todos),
            "todos": todos,
            "results": results,
            "todo_md": todo_md,
            "todo_md_path": todo_md_path,
            "todo_active_id": todo_active_id,
            "active_tools": active_tools,
            "execution_status": "replan",
            "resume_context": _resume_context_after_round(
                state=state,
                config=config,
                todo_active_id=todo_active_id,
                pending_capability=pending_capability,
            ),
            "execution_trace": execution_trace,
            "invocation_dedup": invocation_dedup,
        }

    execution_trace = _append_trace(
        execution_trace,
        stage="level3_replan",
        status="cancelled",
        detail={"decision": "cancel"},
    )
    return {
        "plan": _todo_plan_from_todos(todos),
        "todos": todos,
        "results": results,
        "todo_md": todo_md,
        "todo_md_path": todo_md_path,
        "todo_active_id": todo_active_id,
        "active_tools": active_tools,
        "execution_status": "done",
        "final_answer": "已取消整体重规划，请补充更明确的目标后重试。",
        "resume_context": _resume_context_after_round(
            state=state,
            config=config,
            todo_active_id=todo_active_id,
            pending_capability=pending_capability,
        ),
        "execution_trace": execution_trace,
        "invocation_dedup": invocation_dedup,
    }


def _pick_active_todo(todos: list[dict[str, Any]]) -> dict[str, Any] | None:
    for todo in todos:
        if str(todo.get("status", "pending")) == "pending":
            return todo
    return todos[0] if todos else None


def _capability_entry_id(raw: Any) -> str:
    if isinstance(raw, dict):
        candidates = (
            raw.get("capability_id"),
            raw.get("id"),
            raw.get("tool"),
            raw.get("name"),
        )
        for value in candidates:
            text = str(value or "").strip()
            if text:
                return text
        return ""
    return str(raw or "").strip()


def _capability_entry_type(raw: Any, *, dynamic_tools: dict[str, Any]) -> str:
    if isinstance(raw, dict):
        text = str(raw.get("capability_type") or raw.get("type") or "").strip().lower()
        if text in {"tool", "skill"}:
            return text
    cap_id = _capability_entry_id(raw)
    tool_obj = dynamic_tools.get(cap_id)
    if tool_obj is not None and bool(getattr(tool_obj, "_is_skill_capability", False)):
        return "skill"
    return "tool"


def _normalize_required_capabilities(
    *,
    todo: dict[str, Any] | None,
    dynamic_tools: dict[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(todo, dict):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    raw_caps = list(todo.get("required_capabilities") or [])
    if raw_caps:
        for raw in raw_caps:
            cap_id = _capability_entry_id(raw)
            if not cap_id or cap_id in seen:
                continue
            seen.add(cap_id)
            out.append(
                {
                    "capability_id": cap_id,
                    "capability_type": _capability_entry_type(raw, dynamic_tools=dynamic_tools),
                }
            )
        return out

    for raw in (todo.get("required_tools") or []):
        cap_id = _capability_entry_id(raw)
        if not cap_id or cap_id in seen:
            continue
        seen.add(cap_id)
        out.append({"capability_id": cap_id, "capability_type": "tool"})
    return out


def _compute_effective_tools(
    todo: dict[str, Any] | None,
    *,
    dynamic_tools: dict[str, Any],
    available_capabilities: set[str],
) -> list[str]:
    if not isinstance(todo, dict):
        return []
    required = [item["capability_id"] for item in _normalize_required_capabilities(todo=todo, dynamic_tools=dynamic_tools)]
    blocked = {
        _capability_entry_id(x)
        for x in ((todo.get("blocked_capabilities") or []) + (todo.get("blocked_tools") or []))
        if _capability_entry_id(x)
    }
    if not required:
        required = [
            capability
            for capability in _DEFAULT_CAPABILITY_FALLBACK_ORDER
            if capability in available_capabilities
        ]
    return [tool for tool in required if tool not in blocked]


def _semantic_types_from_todo(todo: dict[str, Any] | None) -> set[str]:
    if not isinstance(todo, dict):
        return set()
    semantic_types: set[str] = set()
    for item in (todo.get("term_context") or []):
        if not isinstance(item, dict):
            continue
        raw = str(item.get("semantic_type") or "").strip().lower()
        if raw:
            semantic_types.add(raw)
    return semantic_types


def _tool_priority_for_semantic(tool_name: str, semantic_types: set[str]) -> int:
    lowered = tool_name.lower()
    score = 100
    # action 语义：优先动作执行类 capability，抑制纯查询类。
    if "action" in semantic_types:
        if any(k in lowered for k in _ACTION_KEYWORDS):
            score -= 45
        elif any(k in lowered for k in _QUERY_KEYWORDS):
            score += 8

    # object/view 语义：优先查询/读取类 capability，抑制动作类。
    if "object" in semantic_types or "view" in semantic_types:
        if any(k in lowered for k in _QUERY_KEYWORDS):
            score -= 35
        elif any(k in lowered for k in _ACTION_KEYWORDS):
            score += 10

    # relation 语义：优先关系解析类；其次允许查询类用于定位主语/宾语。
    if "relation" in semantic_types:
        if any(k in lowered for k in _RELATION_KEYWORDS):
            score -= 50
        elif any(k in lowered for k in _QUERY_KEYWORDS):
            score -= 18
        elif any(k in lowered for k in _ACTION_KEYWORDS):
            score += 12
    return score


def _prioritize_tools_by_semantic(
    todo: dict[str, Any] | None,
    tools: list[str],
) -> list[str]:
    semantic_types = _semantic_types_from_todo(todo)
    if not semantic_types or len(tools) <= 1:
        return tools
    return sorted(
        tools,
        key=lambda tool_name: (_tool_priority_for_semantic(tool_name, semantic_types), tool_name),
    )


def _todo_has_required_capability(todo: dict[str, Any] | None, *, dynamic_tools: dict[str, Any]) -> bool:
    if not isinstance(todo, dict):
        return False
    return bool(_normalize_required_capabilities(todo=todo, dynamic_tools=dynamic_tools))


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


def _normalize_invocation_dedup(values: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


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


def _todo_plan_from_todos(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for todo in todos:
        required_caps = list(todo.get("required_capabilities") or [])
        required_capability_ids = [_capability_entry_id(item) for item in required_caps if _capability_entry_id(item)]
        effective_tools = required_capability_ids or [
            _capability_entry_id(item) for item in (todo.get("required_tools") or []) if _capability_entry_id(item)
        ]
        task_type = (
            str(todo.get("last_capability") or "")
            or (effective_tools[0] if effective_tools else "")
            or (str((todo.get("required_tools") or [""])[0]) if todo.get("required_tools") else "")
        )
        plan.append(
            {
                "id": str(todo.get("todo_id") or ""),
                "type": task_type,
                "description": str(todo.get("goal") or ""),
                "status": str(todo.get("status", "pending")),
                "deps": [str(dep) for dep in (todo.get("depends_on") or [])],
                "params": dict(todo.get("inputs") or {}),
            }
        )
    return plan


def _pick_ready_todo_indexes(todos: list[dict[str, Any]]) -> list[int]:
    done_ids = {
        str(todo.get("todo_id", ""))
        for todo in todos
        if str(todo.get("status", "pending")) in _TODO_DONE_STATES
    }
    ready_indexes: list[int] = []
    pending_indexes: list[int] = []
    for idx, todo in enumerate(todos):
        status = str(todo.get("status", "pending"))
        if status != "pending":
            continue
        pending_indexes.append(idx)
        deps = [str(dep) for dep in (todo.get("depends_on") or [])]
        if all(dep in done_ids for dep in deps):
            ready_indexes.append(idx)
    if ready_indexes:
        return ready_indexes
    if pending_indexes:
        return [pending_indexes[0]]
    return []


async def _store_result_entry(
    *,
    todo_id: str,
    output: Any,
    workspace_dir: str | None,
    is_multi_task: bool,
) -> dict[str, Any]:
    payload = normalize_workspace_task_output(output)
    if is_multi_task and workspace_dir:
        temp_dir = Path(workspace_dir) / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = temp_dir / f"{todo_id}.json"
        await anyio.Path(file_path).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"task_id": todo_id, "file_path": str(file_path)}
    return {"task_id": todo_id, "data": payload}


async def _read_todo_md(workspace_dir: str | None) -> str | None:
    """Read ``temp/todo.md`` and silently degrade when unavailable."""
    if not workspace_dir:
        return None
    todo_path = anyio.Path(Path(workspace_dir) / "temp" / "todo.md")
    try:
        return await todo_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _format_observe(output: Any) -> str | None:
    if output is None:
        return None
    if isinstance(output, str):
        text = output.strip()
    else:
        try:
            text = json.dumps(output, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(output)
    text = text.strip()
    if not text:
        return None
    if len(text) > 2000:
        return text[:2000]
    return text


def _apply_param_overrides(todo: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply LLM parameter overrides into todo inputs (shallow merge)."""
    if not overrides:
        return todo
    current_inputs = todo.get("inputs")
    merged_inputs = dict(current_inputs) if isinstance(current_inputs, dict) else {}
    merged_inputs.update(overrides)
    return {**todo, "inputs": merged_inputs}


def _fields_from_mapping(raw_fields: Any) -> list[str]:
    if isinstance(raw_fields, str):
        value = raw_fields.strip()
        return [value] if value else []
    if isinstance(raw_fields, (list, tuple, set)):
        out: list[str] = []
        for item in raw_fields:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _result_output_payload(entry: dict[str, Any]) -> dict[str, Any]:
    raw_data = entry.get("data")
    if isinstance(raw_data, dict):
        return raw_data

    file_path = entry.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (OSError, json.JSONDecodeError, ValueError):
            return {}
    return {}


def _build_completed_todos_map(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("task_id") or "").strip()
        if not task_id:
            continue
        completed[task_id] = {"output": _result_output_payload(entry)}
    return completed


def _inject_params_from_deps(
    todo: dict[str, Any],
    completed_todos: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Inject fields from dependency outputs into current todo inputs/tool_params."""
    raw_mapping = todo.get("param_from_deps")
    if not isinstance(raw_mapping, dict) or not raw_mapping:
        return todo

    injected_params: dict[str, Any] = {}
    for dep_id, fields in raw_mapping.items():
        dep_key = str(dep_id).strip()
        if not dep_key:
            continue
        dep_output = (completed_todos.get(dep_key) or {}).get("output")
        if not isinstance(dep_output, dict):
            continue
        for field in _fields_from_mapping(fields):
            if field in dep_output:
                injected_params[field] = dep_output[field]

    if not injected_params:
        return todo

    existing_inputs = dict(todo.get("inputs") or {}) if isinstance(todo.get("inputs"), dict) else {}
    existing_tool_params = (
        dict(todo.get("tool_params") or {}) if isinstance(todo.get("tool_params"), dict) else {}
    )
    return {
        **todo,
        "inputs": {**existing_inputs, **injected_params},
        "tool_params": {**existing_tool_params, **injected_params},
    }


def _task_from_todo(todo: dict[str, Any], capability: str) -> dict[str, Any]:
    todo_id = str(todo.get("todo_id") or "")
    return {
        "id": todo_id,
        "type": capability,
        "status": "pending",
        "deps": [str(dep) for dep in (todo.get("depends_on") or [])],
        "params": dict(todo.get("inputs") or {}),
        "description": str(todo.get("goal") or ""),
    }


def _extract_appended_todos(
    *,
    output: Any,
    existing_todos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(output, dict):
        return []
    raw_items = output.get("todo_append") or output.get("todos_append")
    if not isinstance(raw_items, list):
        return []

    appended: list[dict[str, Any]] = []
    used_ids = {str(todo.get("todo_id") or "") for todo in existing_todos}
    next_index = len(existing_todos) + 1
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        goal = str(item.get("goal") or "").strip()
        raw_required_capability_items = (
            item.get("required_capabilities")
            if isinstance(item.get("required_capabilities"), list)
            else item.get("required_tools")
        )
        required_capability_items: list[Any] = (
            raw_required_capability_items if isinstance(raw_required_capability_items, list) else []
        )
        required_tools = [_capability_entry_id(v) for v in required_capability_items if _capability_entry_id(v)]
        required_capabilities = []
        for v in required_capability_items:
            cap_id = _capability_entry_id(v)
            if not cap_id:
                continue
            if isinstance(v, dict):
                cap_type = str(v.get("capability_type") or v.get("type") or "tool")
            else:
                cap_type = "tool"
            required_capabilities.append({"capability_id": cap_id, "capability_type": cap_type})
        if not goal or not required_tools:
            continue

        todo_id = str(item.get("todo_id") or "").strip()
        while not todo_id or todo_id in used_ids:
            todo_id = f"t_add_{next_index}"
            next_index += 1
        used_ids.add(todo_id)

        appended.append(
            {
                "todo_id": todo_id,
                "goal": goal,
                "required_tools": required_tools,
                "blocked_tools": [str(v).strip() for v in (item.get("blocked_tools") or []) if str(v).strip()],
                "required_capabilities": required_capabilities,
                "blocked_capabilities": [_capability_entry_id(v) for v in (item.get("blocked_capabilities") or []) if _capability_entry_id(v)],
                "inputs": dict(item.get("inputs") or {}),
                "depends_on": [str(v).strip() for v in (item.get("depends_on") or []) if str(v).strip()],
                "term_context": [x for x in (item.get("term_context") or []) if isinstance(x, dict)],
                "acceptance_criteria": str(item.get("acceptance_criteria") or "appended todo completed"),
                "status": "pending",
            }
        )
    return appended


async def _execute_one_todo(
    *,
    todo: dict[str, Any],
    state: AgentState,
    query_mode: str,
    runtime: ToolRuntime,
    dynamic_tools: dict[str, Any],
    available_capabilities: set[str],
    invocation_dedup_set: set[str],
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str], list[dict[str, Any]], bool]:
    todo_id = str(todo.get("todo_id") or "")
    effective_tools = _compute_effective_tools(
        todo,
        dynamic_tools=dynamic_tools,
        available_capabilities=available_capabilities,
    )
    effective_tools = _prioritize_tools_by_semantic(todo, effective_tools)
    has_required = _todo_has_required_capability(todo, dynamic_tools=dynamic_tools)
    trace: list[dict[str, Any]] = []
    invocation_add: list[str] = []

    if has_required and not effective_tools:
        blocked_todo = {**todo, "status": "blocked"}
        trace.append(
            {
                "stage": "execution",
                "status": "blocked",
                "detail": {"todo_id": todo_id, "reason": "no_effective_tools"},
            }
        )
        return blocked_todo, None, invocation_add, trace, True

    if not effective_tools:
        skipped_todo = {**todo, "status": "skipped"}
        trace.append(
            {
                "stage": "execution",
                "status": "skipped",
                "detail": {"todo_id": todo_id, "reason": "no_required_capability"},
            }
        )
        return skipped_todo, None, invocation_add, trace, False

    remaining_capabilities = list(effective_tools)
    react_round = 0
    max_rounds = _get_react_max_rounds(state)
    last_output: Any = None
    workspace_dir = str(state.get("workspace_dir") or "") or None
    while remaining_capabilities and react_round < max_rounds:
        react_round += 1
        todo_md_summary = await _read_todo_md(workspace_dir)
        observe_text = _format_observe(last_output)
        selection = await select_react_capability(
            state=state,
            todo=todo,
            candidates=remaining_capabilities,
            round_index=react_round,
            todo_md_summary=todo_md_summary,
            observe=observe_text,
        )
        param_overrides = selection.get("param_overrides")
        if isinstance(param_overrides, dict) and param_overrides:
            todo = _apply_param_overrides(todo, param_overrides)
            trace.append(
                {
                    "stage": "react_round",
                    "status": "param_overrides_applied",
                    "detail": {
                        "todo_id": todo_id,
                        "round": react_round,
                        "override_keys": sorted(str(k) for k in param_overrides.keys()),
                    },
                }
            )
        capability = str(selection.get("capability_id") or "").strip()
        if capability not in remaining_capabilities:
            capability = remaining_capabilities[0]
            selection = {
                "capability_id": capability,
                "source": "fallback",
                "reason": "selector_out_of_candidates",
                "tool_call_id": None,
                "param_overrides": {},
            }
        remaining_capabilities = [x for x in remaining_capabilities if x != capability]
        trace.append(
            {
                "stage": "react_round",
                "status": "selected",
                "detail": {
                    "todo_id": todo_id,
                    "round": react_round,
                    "candidate_count": len(effective_tools),
                    "selected_capability": capability,
                    "selection_source": str(selection.get("source") or ""),
                    "tool_call_id": str(selection.get("tool_call_id") or ""),
                    "selection_reason": str(selection.get("reason") or ""),
                },
            }
        )

        invocation_id = _build_invocation_id(
            query_mode=query_mode,
            target_tool=capability,
            tool_params=cast(dict[str, Any], todo.get("inputs") or {}),
            todo_active_id=todo_id,
        )
        if invocation_id in invocation_dedup_set:
            trace.append(
                {
                    "stage": "execution",
                    "status": "dedup_skipped",
                    "detail": {"todo_id": todo_id, "capability": capability},
                }
            )
            return (
                {**todo, "status": "done", "last_capability": capability},
                None,
                invocation_add,
                trace,
                False,
            )

        task = _task_from_todo(todo, capability)
        updated_task, output = await runtime.invoke_with_callbacks(task, state)
        task_status = str(updated_task.get("status", "failed"))
        trace.append(
            {
                "stage": "execution",
                "status": task_status,
                "detail": {"todo_id": todo_id, "capability": capability},
            }
        )
        if task_status == "done":
            invocation_add.append(invocation_id)
            return (
                {**todo, "status": "done", "last_capability": capability},
                {"task_id": todo_id, "output": output},
                invocation_add,
                trace,
                False,
            )
        trace.append(
            {
                "stage": "react_round",
                "status": "observe_failed",
                "detail": {
                    "todo_id": todo_id,
                    "round": react_round,
                    "capability": capability,
                    "error": str(updated_task.get("error", "task_failed")),
                },
            }
        )
        last_output = output

    failed_todo = {
        **todo,
        "status": "failed",
        "error": "all_capabilities_failed",
        "last_capability": effective_tools[-1],
    }
    return failed_todo, None, invocation_add, trace, False


def _ensure_direct_todo_from_route(
    state: AgentState,
    *,
    dynamic_tools: dict[str, Any],
) -> list[dict[str, Any]]:
    current_todos = list(state.get("todos") or [])
    if current_todos:
        return current_todos
    target_tool = str(state.get("target_tool") or "").strip()
    if not target_tool:
        return []
    capability_type = (
        "skill"
        if bool(getattr(dynamic_tools.get(target_tool), "_is_skill_capability", False))
        else "tool"
    )
    return [
        {
            "todo_id": "t_direct",
            "goal": str(state.get("intent") or state.get("user_query") or ""),
            "required_tools": [target_tool],
            "blocked_tools": [],
            "required_capabilities": [
                {"capability_id": target_tool, "capability_type": capability_type}
            ],
            "blocked_capabilities": [],
            "inputs": dict(state.get("tool_params") or {}),
            "depends_on": [],
            "term_context": [],
            "acceptance_criteria": "direct tool completed",
            "status": "pending",
        }
    ]


def _resume_context_after_round(
    *,
    state: AgentState,
    config: RunnableConfig,
    todo_active_id: str,
    pending_capability: str,
) -> dict[str, Any]:
    previous = dict(state.get("resume_context") or {})
    configurable = config.get("configurable") or {}
    previous["thread_id"] = str(configurable.get("thread_id") or previous.get("thread_id") or "")
    previous["todo_active_id"] = todo_active_id
    previous["react_step_id"] = todo_active_id
    previous["pending_capability"] = pending_capability
    return previous


async def execution_node(
    state: AgentState,
    config: RunnableConfig,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one dependency-ready todo batch and decide next step."""
    gateway_context = (config.get("configurable") or {}).get("gateway_context")
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    runtime = ToolRuntime(custom_tools=dynamic_tools, gateway_context=gateway_context)
    available_capabilities = set(dynamic_tools.keys()) | set(_BUILTIN_EXECUTOR_CAPABILITIES)
    todos = _ensure_direct_todo_from_route(state, dynamic_tools=dynamic_tools)
    existing_todo_md_path = (
        str(state.get("todo_md_path")) if state.get("todo_md_path") else None
    )
    invocation_dedup = _normalize_invocation_dedup(cast(list[Any] | None, state.get("invocation_dedup")))
    invocation_dedup_set = set(invocation_dedup)
    execution_trace = list(state.get("execution_trace") or [])
    query_mode = str(state.get("query_mode") or "analysis")

    active_todo = _pick_active_todo(todos)
    todo_active_id = str(active_todo.get("todo_id", "")) if active_todo else ""
    active_tools = _compute_effective_tools(
        active_todo,
        dynamic_tools=dynamic_tools,
        available_capabilities=available_capabilities,
    )
    active_tools = _prioritize_tools_by_semantic(active_todo, active_tools)
    pending_capability = active_tools[0] if active_tools else ""

    if state.get("ambiguous_terms"):
        updates = await _handle_ambiguous_terms(
            state,
            todo_active_id=todo_active_id,
            pending_capability=pending_capability,
        )
        if updates.get("ambiguous_terms"):
            return {
                **updates,
                "todo_active_id": todo_active_id,
                "active_tools": active_tools,
                "execution_status": "done",
                "resume_context": _resume_context_after_round(
                    state=state,
                    config=config,
                    todo_active_id=todo_active_id,
                    pending_capability=pending_capability,
                ),
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
            "active_tools": active_tools,
            "execution_status": "replan",
            "resume_context": _resume_context_after_round(
                state=state,
                config=config,
                todo_active_id=todo_active_id,
                pending_capability=pending_capability,
            ),
            "execution_trace": _append_trace(
                execution_trace,
                stage="clarification",
                status="resolved",
                detail={"todo_id": todo_active_id},
            ),
            "invocation_dedup": invocation_dedup,
        }

    if query_mode == "chitchat" or bool(state.get("clarify_needed")):
        return {
            "todos": todos,
            "todo_active_id": todo_active_id,
            "active_tools": active_tools,
            "execution_status": "done",
            "resume_context": _resume_context_after_round(
                state=state,
                config=config,
                todo_active_id=todo_active_id,
                pending_capability=pending_capability,
            ),
            "execution_trace": _append_trace(
                execution_trace,
                stage="execution",
                status="done",
                detail={"query_mode": query_mode},
            ),
            "invocation_dedup": invocation_dedup,
        }

    if not todos:
        return {
            "plan": [],
            "todos": [],
            "todo_active_id": "",
            "active_tools": [],
            "execution_status": "done",
            "resume_context": _resume_context_after_round(
                state=state,
                config=config,
                todo_active_id="",
                pending_capability="",
            ),
            "execution_trace": _append_trace(
                execution_trace,
                stage="execution",
                status="done",
                detail={"reason": "empty_todos"},
            ),
            "invocation_dedup": invocation_dedup,
        }

    dependency_deadlock = _has_dependency_deadlock(todos)
    if dependency_deadlock:
        deadlocked = [
            {**todo, "status": "failed"} if str(todo.get("status", "")) == "pending" else todo
            for todo in todos
        ]
        todo_md = _todo_md_with_status(deadlocked)
        todo_md_path = _persist_todo_md(
            workspace_dir=state.get("workspace_dir"),
            todo_md=todo_md,
            existing_path=existing_todo_md_path,
        )
        execution_trace = _append_trace(
            execution_trace,
            stage="level3_replan",
            status="interrupt",
            detail={"reason": "dependency_deadlock"},
        )
        resume_value = interrupt(
            _build_level3_interrupt_payload(
                todo_active_id=todo_active_id,
                pending_capability=pending_capability,
                interrupt_reason="dependency_deadlock",
            )
        )
        return _build_level3_result(
            confirmed=_parse_level3_confirmation(resume_value),
            state=state,
            config=config,
            todos=deadlocked,
            results=list(state.get("results") or []),
            todo_md=todo_md,
            todo_md_path=todo_md_path,
            todo_active_id=todo_active_id,
            active_tools=active_tools,
            pending_capability=pending_capability,
            execution_trace=execution_trace,
            invocation_dedup=invocation_dedup,
        )

    ready_indexes = _pick_ready_todo_indexes(todos)
    results = list(state.get("results") or [])
    completed_todos_map = _build_completed_todos_map(results)
    ready_todos = [_inject_params_from_deps(todos[idx], completed_todos_map) for idx in ready_indexes]
    for idx, todo in zip(ready_indexes, ready_todos, strict=False):
        todos[idx] = todo

    multi_task = len(todos) > 1
    batch_outputs = await asyncio.gather(
        *[
            _execute_one_todo(
                todo=todo,
                state=state,
                query_mode=query_mode,
                runtime=runtime,
                dynamic_tools=dynamic_tools,
                available_capabilities=available_capabilities,
                invocation_dedup_set=invocation_dedup_set,
            )
            for todo in ready_todos
        ]
    )

    blocked_in_batch = False
    appended_todos: list[dict[str, Any]] = []
    for idx, (updated_todo, maybe_output, invocation_add, todo_trace, blocked) in zip(
        ready_indexes, batch_outputs, strict=False
    ):
        todos[idx] = updated_todo
        blocked_in_batch = blocked_in_batch or blocked
        for event in todo_trace:
            execution_trace = _append_trace(
                execution_trace,
                stage=str(event.get("stage", "execution")),
                status=str(event.get("status", "unknown")),
                detail=cast(dict[str, Any] | None, event.get("detail")),
            )
        for invocation_id in invocation_add:
            text_id = str(invocation_id).strip()
            if text_id and text_id not in invocation_dedup_set:
                invocation_dedup.append(text_id)
                invocation_dedup_set.add(text_id)
        if maybe_output is not None:
            entry = await _store_result_entry(
                todo_id=str(maybe_output.get("task_id", "")),
                output=maybe_output.get("output"),
                workspace_dir=state.get("workspace_dir"),
                is_multi_task=multi_task,
            )
            results.append(entry)
            todo_result_output = maybe_output.get("output")
            completed_todos_map[str(maybe_output.get("task_id") or "")] = {
                "output": todo_result_output if isinstance(todo_result_output, dict) else {}
            }
            append_items = _extract_appended_todos(
                output=maybe_output.get("output"),
                existing_todos=todos + appended_todos,
            )
            if append_items:
                appended_todos.extend(append_items)
                execution_trace = _append_trace(
                    execution_trace,
                    stage="react_replanning",
                    status="append_todo",
                    detail={
                        "plugin_id": "react_replanning",
                        "risk_level": "medium",
                        "todo_id": str(updated_todo.get("todo_id") or ""),
                        "append_count": len(append_items),
                    },
                )

    if appended_todos:
        todos.extend(appended_todos)

    failed_ids = {
        str(todo.get("todo_id") or "")
        for todo in todos
        if str(todo.get("status", "")) == "failed"
    }
    for idx, todo in enumerate(todos):
        if str(todo.get("status", "pending")) != "pending":
            continue
        deps = [str(dep) for dep in (todo.get("depends_on") or [])]
        if deps and any(dep in failed_ids for dep in deps):
            todos[idx] = {**todo, "status": "skipped", "note": "dependency_failed"}
            execution_trace = _append_trace(
                execution_trace,
                stage="execution",
                status="skipped",
                detail={"todo_id": str(todo.get("todo_id") or ""), "reason": "dependency_failed"},
            )

    next_active_todo = _pick_active_todo(todos)
    next_todo_id = str(next_active_todo.get("todo_id", "")) if next_active_todo else ""
    next_active_tools = _compute_effective_tools(
        next_active_todo,
        dynamic_tools=dynamic_tools,
        available_capabilities=available_capabilities,
    )
    next_active_tools = _prioritize_tools_by_semantic(next_active_todo, next_active_tools)
    next_pending_capability = next_active_tools[0] if next_active_tools else ""
    has_pending = any(str(todo.get("status", "pending")) == "pending" for todo in todos)

    todo_md = _todo_md_with_status(todos)
    todo_md_path = _persist_todo_md(
        workspace_dir=state.get("workspace_dir"),
        todo_md=todo_md,
        existing_path=existing_todo_md_path,
    )

    failure_trigger = _should_trigger_level3(state, todos)
    unreachable_trigger = _is_overall_unreachable(todos)
    if failure_trigger or unreachable_trigger:
        trigger_reason = "failed_threshold_reached" if failure_trigger else "overall_unreachable"
        execution_trace = _append_trace(
            execution_trace,
            stage="level3_replan",
            status="interrupt",
            detail={"reason": trigger_reason},
        )
        resume_value = interrupt(
            _build_level3_interrupt_payload(
                todo_active_id=next_todo_id,
                pending_capability=next_pending_capability,
                interrupt_reason=trigger_reason,
            )
        )
        return _build_level3_result(
            confirmed=_parse_level3_confirmation(resume_value),
            state=state,
            config=config,
            todos=todos,
            results=results,
            todo_md=todo_md,
            todo_md_path=todo_md_path,
            todo_active_id=next_todo_id,
            active_tools=next_active_tools,
            pending_capability=next_pending_capability,
            execution_trace=execution_trace,
            invocation_dedup=invocation_dedup,
        )

    execution_status = "replan" if blocked_in_batch else ("execution" if has_pending else "done")

    return {
        "plan": _todo_plan_from_todos(todos),
        "todos": todos,
        "results": results,
        "todo_md": todo_md,
        "todo_md_path": todo_md_path,
        "todo_active_id": next_todo_id,
        "active_tools": next_active_tools,
        "execution_status": execution_status,
        "resume_context": _resume_context_after_round(
            state=state,
            config=config,
            todo_active_id=next_todo_id,
            pending_capability=next_pending_capability,
        ),
        "execution_trace": execution_trace,
        "invocation_dedup": invocation_dedup,
    }

