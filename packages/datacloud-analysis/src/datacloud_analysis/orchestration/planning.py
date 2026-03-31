"""Planning node for the 5-node main pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from datacloud_analysis.orchestration.dag import dag_node
from datacloud_analysis.orchestration.intent import intent_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)
_PLANNER_BUILTIN_CAPABILITIES: frozenset[str] = frozenset(
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


def _semantic_type_from_term(term: dict[str, Any]) -> str:
    raw = str(term.get("term_type_code", "")).upper()
    if "ACTION" in raw:
        return "action"
    if "RELATION" in raw:
        return "relation"
    if "VIEW" in raw:
        return "view"
    return "object"


def _build_term_context(confirmed_terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for term in confirmed_terms:
        out.append(
            {
                "mention": str(term.get("mention", "")),
                "normalized_term": str(term.get("term_name", "")),
                "term_id": str(term.get("term_id", "")),
                "confidence": float(term.get("confidence", 0.0) or 0.0),
                "source": str(term.get("source", "llm_infer")),
                "semantic_type": _semantic_type_from_term(term),
                "note": "",
            }
        )
    return out


def _build_term_context_from_hints(term_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hint in term_hints:
        confidence = float(hint.get("confidence", 0.0) or 0.0)
        mention = str(hint.get("mention", "")).strip()
        normalized = str(hint.get("normalized_term", mention)).strip()
        semantic_type = str(hint.get("semantic_type", "")).strip() or _semantic_type_from_term(hint)
        if not mention and not normalized:
            continue
        out.append(
            {
                "mention": mention or normalized,
                "normalized_term": normalized or mention,
                "term_id": str(hint.get("term_id", "")).strip(),
                "confidence": confidence,
                "source": str(hint.get("source", "knowledge_match")),
                "semantic_type": semantic_type,
                "note": str(hint.get("note", "")),
            }
        )
    return out


def _merge_term_context(
    confirmed: list[dict[str, Any]],
    hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in confirmed + hints:
        mention = str(item.get("mention", "")).strip()
        term_id = str(item.get("term_id", "")).strip()
        key = (mention, term_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _capability_spec(capability_id: str, available_tools: dict[str, Any]) -> dict[str, str]:
    tool_obj = available_tools.get(capability_id)
    capability_type = "skill" if bool(getattr(tool_obj, "_is_skill_capability", False)) else "tool"
    return {"capability_id": capability_id, "capability_type": capability_type}


def _is_available_capability(capability_id: str, available_tools: dict[str, Any]) -> bool:
    return capability_id in available_tools or capability_id in _PLANNER_BUILTIN_CAPABILITIES


def _plan_to_todos(
    *,
    plan: list[dict[str, Any]],
    available_tools: dict[str, Any],
    term_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    todos: list[dict[str, Any]] = []
    for idx, task in enumerate(plan, start=1):
        task_id = str(task.get("id") or f"t{idx}")
        task_type = str(task.get("type") or "")
        status = str(task.get("status") or "pending")
        is_unavailable = bool(task_type) and not _is_available_capability(task_type, available_tools)
        required_tools = [task_type] if task_type else []
        required_capabilities = (
            [_capability_spec(task_type, available_tools)] if task_type else []
        )
        blocked_tools = [task_type] if is_unavailable else []
        blocked_capabilities = (
            [_capability_spec(task_type, available_tools)] if is_unavailable and task_type else []
        )
        todo = {
            "todo_id": task_id,
            "goal": str(task.get("description") or ""),
            "required_tools": required_tools,
            "blocked_tools": blocked_tools,
            "required_capabilities": required_capabilities,
            "blocked_capabilities": blocked_capabilities,
            "inputs": dict(task.get("params") or {}),
            "depends_on": [str(x) for x in (task.get("deps") or [])],
            "term_context": term_context,
            "acceptance_criteria": f"task {task_id} executed successfully",
            "status": status,
        }
        todos.append(todo)
        if is_unavailable:
            logger.warning(
                "planning_node: task capability unavailable and temporarily blocked task_id=%s capability=%s",
                task_id,
                task_type,
            )
    return todos


def _direct_todo_from_route(
    *,
    query_mode: str,
    target_tool: str,
    tool_params: dict[str, Any],
    intent_text: str,
    available_tools: dict[str, Any],
    term_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if query_mode not in {"online_query", "agent_delegate"} or not target_tool:
        return []
    direct_inputs = dict(tool_params)
    if query_mode == "agent_delegate" and "delegate_policy" not in direct_inputs:
        direct_inputs["delegate_policy"] = {"mode": "sync", "wait_for_reply": True}
    return [
        {
            "todo_id": "t_direct",
            "goal": intent_text,
            "required_tools": [target_tool],
            "blocked_tools": [],
            "required_capabilities": [_capability_spec(target_tool, available_tools)],
            "blocked_capabilities": [],
            "inputs": direct_inputs,
            "depends_on": [],
            "term_context": term_context,
            "acceptance_criteria": "direct tool completed",
            "status": "pending",
        }
    ]


def _build_todo_md(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "# TODOs\n\n- (empty)\n"
    lines = ["# TODOs", ""]
    for todo in todos:
        lines.append(f"- [{todo.get('status', 'pending')}] {todo.get('todo_id', '')}: {todo.get('goal', '')}")
        lines.append(f"  required_tools: {todo.get('required_tools', [])}")
        lines.append(f"  depends_on: {todo.get('depends_on', [])}")
    lines.append("")
    return "\n".join(lines)


def _persist_todo_md(workspace_dir: str | None, todo_md: str) -> str | None:
    if not workspace_dir:
        return None
    try:
        path = Path(workspace_dir) / "temp" / "todo.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(todo_md, encoding="utf-8")
        return str(path)
    except OSError as exc:
        logger.warning("planning_node: failed to persist todo.md: %s", exc)
        return None


async def planning_node(
    state: AgentState,
    gateway_context: Any = None,
    default_prompts: dict[str, Any] | None = None,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan todos using intent classification + optional DAG decomposition."""
    query_input = str(
        state.get("intent")
        or state.get("enriched_query")
        or state.get("user_query")
        or ""
    ).strip()
    if not query_input:
        return {"todos": [], "todo_md": "# TODOs\n\n- (empty)\n"}

    intent_updates = await intent_node(
        state,
        gateway_context=gateway_context,
        default_prompts=default_prompts,
        default_tools=default_tools,
        query_override=query_input,
    )
    query_mode = str(intent_updates.get("query_mode") or "analysis")
    intent_text = str(intent_updates.get("intent") or query_input)
    target_tool = str(intent_updates.get("target_tool") or "")
    raw_tool_params = intent_updates.get("tool_params")
    tool_params = raw_tool_params if isinstance(raw_tool_params, dict) else {}
    available_tools = state.get("dynamic_tools") or default_tools or {}
    confirmed_terms = list(intent_updates.get("confirmed_terms") or [])
    term_hints = list(intent_updates.get("term_hints") or state.get("term_hints") or [])
    term_context = _merge_term_context(
        _build_term_context(confirmed_terms),
        _build_term_context_from_hints(term_hints),
    )

    if query_mode in {"online_query", "agent_delegate"}:
        tool_fn = available_tools.get(target_tool)
        tool_valid = bool(tool_fn)
        is_delegate_tool = bool(tool_fn and getattr(tool_fn, "_is_agent_delegate", False))

        if not tool_valid:
            logger.warning(
                "planning_node: invalid target tool for mode=%s target=%r, fallback to analysis",
                query_mode,
                target_tool,
            )
            query_mode = "analysis"
            intent_updates["query_mode"] = "analysis"
            intent_updates["target_tool"] = ""
            target_tool = ""
        elif query_mode == "online_query" and is_delegate_tool:
            # Delegate tools should use the dedicated delegation path for gateway hand-off.
            query_mode = "agent_delegate"
            intent_updates["query_mode"] = "agent_delegate"
        elif query_mode == "agent_delegate" and not is_delegate_tool:
            # Non-delegate tools should run through direct tool invocation.
            query_mode = "online_query"
            intent_updates["query_mode"] = "online_query"

    plan: list[dict[str, Any]] = []
    if query_mode == "analysis" and not intent_updates.get("ambiguous_terms"):
        merged_state = cast(AgentState, {**state, **intent_updates})
        dag_updates = await dag_node(
            merged_state,
            gateway_context=gateway_context,
            default_prompts=default_prompts,
            default_tools=default_tools,
        )
        plan = list(dag_updates.get("plan", []) or [])
    else:
        plan = []

    todos = _plan_to_todos(plan=plan, available_tools=available_tools, term_context=term_context)
    if not todos:
        todos = _direct_todo_from_route(
            query_mode=query_mode,
            target_tool=target_tool,
            tool_params=tool_params,
            intent_text=intent_text,
            available_tools=available_tools,
            term_context=term_context,
        )
    todo_md = _build_todo_md(todos)
    todo_md_path = _persist_todo_md(state.get("workspace_dir"), todo_md)

    return {
        **intent_updates,
        "plan": plan,
        "todos": todos,
        "todo_md": todo_md,
        "todo_md_path": todo_md_path,
    }
