"""Planning node for the 5-node main pipeline."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from datacloud_analysis.orchestration.planning.decomposer import (
    decompose_analysis_plan,
    expand_relation_todos,
)
from datacloud_analysis.orchestration.planning.facade import resolve_planning_context
from datacloud_analysis.orchestration.shared import PlanTask
from datacloud_analysis.orchestration.state import (
    AgentState,
    ensure_blocked_task,
    ensure_multitask_defaults,
    set_planned_tasks,
    set_task_queue,
)

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


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, Iterable):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _log_inputs_warning(todo_id: str, param: str, detail: str) -> None:
    logger.warning(
        "planning_node: invalid inputs_from entry todo_id=%s param=%s detail=%s",
        todo_id,
        param,
        detail,
    )


def _parse_inputs_spec(raw_task: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, bool]]:
    raw_inputs = raw_task.get("inputs_from")
    if raw_inputs is None and isinstance(raw_task.get("params"), Mapping):
        raw_inputs = raw_task["params"].get("inputs_from")

    inputs_from: dict[str, str] = {}
    required_inputs: dict[str, bool] = {}

    if isinstance(raw_inputs, Mapping):
        iterator = raw_inputs.items()
    elif isinstance(raw_inputs, list):
        iterator = []
        for item in raw_inputs:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                value = item.get("path") or item.get("value")
                iterator.append((name, value))
    else:
        iterator = []

    for key, spec in iterator:
        param = str(key or "").strip()
        if not param:
            continue
        if isinstance(spec, Mapping):
            path = str(spec.get("path") or spec.get("value") or "").strip()
            required = bool(spec.get("required"))
        else:
            path = str(spec or "").strip()
            required = False
        if not path:
            _log_inputs_warning(
                str(raw_task.get("id") or param),
                param,
                "missing path",
            )
            continue
        inputs_from[param] = path
        if required:
            required_inputs[param] = True

    return inputs_from, required_inputs


def _extract_dependency_from_expr(expr: str) -> str | None:
    cleaned = str(expr or "").strip()
    if not cleaned:
        return None
    cutoff = len(cleaned)
    dot_index = cleaned.find(".")
    bracket_index = cleaned.find("[")
    if dot_index != -1:
        cutoff = min(cutoff, dot_index)
    if bracket_index != -1:
        cutoff = min(cutoff, bracket_index)
    source = cleaned[:cutoff].strip()
    return source or None


def _plan_tasks_from_analysis_plan(
    plan: list[dict[str, Any]],
) -> list[PlanTask]:
    tasks: list[PlanTask] = []
    seen_ids: set[str] = set()
    for idx, raw_task in enumerate(plan, start=1):
        todo_id = str(raw_task.get("id") or f"t{idx}").strip()
        if not todo_id:
            todo_id = f"t{idx}"
        base_id = todo_id
        suffix = 1
        while todo_id in seen_ids:
            suffix += 1
            todo_id = f"{base_id}_{suffix}"
        seen_ids.add(todo_id)

        inputs_from, required_inputs = _parse_inputs_spec(raw_task)
        depends_on = _coerce_str_list(raw_task.get("deps"))
        required_tools = _coerce_str_list([raw_task.get("type")])
        task = PlanTask(
            todo_id=todo_id,
            goal=str(raw_task.get("description") or ""),
            required_tools=required_tools,
            depends_on=depends_on,
            inputs_from=inputs_from,
            required_inputs=required_inputs,
        )
        tasks.append(task)
    return tasks


def _direct_plan_task(
    todo_id: str,
    goal: str,
    tool: str,
) -> PlanTask:
    return PlanTask(
        todo_id=todo_id,
        goal=goal,
        required_tools=[tool] if tool else [],
        depends_on=[],
        inputs_from={},
        required_inputs={},
    )


def _resolve_dependency_graph(
    tasks: list[PlanTask],
) -> tuple[list[str], dict[str, str]]:
    """Return topological order and blocked reasons by todo_id."""
    task_map = {task.todo_id: task for task in tasks}
    blocked_by: dict[str, str] = {}

    for task in tasks:
        normalized: list[str] = []
        seen: set[str] = set()
        for dep in task.depends_on:
            dep_id = dep.strip()
            if not dep_id:
                continue
            if dep_id not in task_map:
                blocked_by[task.todo_id] = "missing_dependency"
                _log_inputs_warning(task.todo_id, dep_id, "dependency not found")
                continue
            if dep_id == task.todo_id or dep_id in seen:
                continue
            seen.add(dep_id)
            normalized.append(dep_id)

        for expr in task.inputs_from.values():
            dep_id = _extract_dependency_from_expr(expr)
            if not dep_id or dep_id == task.todo_id:
                continue
            if dep_id not in task_map:
                blocked_by.setdefault(task.todo_id, "missing_dependency")
                _log_inputs_warning(
                    task.todo_id,
                    expr,
                    "inputs_from dependency not found",
                )
                continue
            if dep_id not in normalized:
                normalized.append(dep_id)
        task.depends_on = normalized

    indegree: dict[str, int] = defaultdict(int)
    adjacency: dict[str, list[str]] = {task_id: [] for task_id in task_map}
    active_nodes = [tid for tid in task_map if tid not in blocked_by]

    for task in tasks:
        if task.todo_id in blocked_by:
            continue
        for dep in task.depends_on:
            if dep in blocked_by:
                blocked_by[task.todo_id] = "missing_dependency"
                break
            adjacency.setdefault(dep, []).append(task.todo_id)
            indegree[task.todo_id] += 1
    queue = deque([tid for tid in active_nodes if indegree.get(tid, 0) == 0])
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for follower in adjacency.get(node, []):
            indegree[follower] -= 1
            if indegree[follower] == 0:
                queue.append(follower)
    residual = [tid for tid in active_nodes if tid not in order]
    for tid in residual:
        blocked_by[tid] = "cycle_detected"
        logger.warning("planning_node: detected cycle involving task_id=%s", tid)
    return order, blocked_by


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
        is_unavailable = bool(task_type) and not _is_available_capability(
            task_type, available_tools
        )
        required_tools = [task_type] if task_type else []
        required_capabilities = [_capability_spec(task_type, available_tools)] if task_type else []
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
        lines.append(
            f"- [{todo.get('status', 'pending')}] {todo.get('todo_id', '')}: {todo.get('goal', '')}"
        )
        lines.append(f"  required_tools: {todo.get('required_tools', [])}")
        lines.append(f"  depends_on: {todo.get('depends_on', [])}")
    lines.append("")
    return "\n".join(lines)


def _tool_kind_for_log(name: str, obj: Any) -> str:
    """Return a short label for logging tool/skill/delegate kind."""
    if getattr(obj, "_is_agent_delegate", False):
        return "agent_delegate"
    if getattr(obj, "_is_skill_capability", False):
        return "skill"
    return "tool"


def _log_planning_injected_tools(
    *,
    state: AgentState,
    default_tools: dict[str, Any] | None,
    available_tools: dict[str, Any],
) -> None:
    """Log which tool dict planning uses and per-key kind for debugging."""
    raw_dynamic = state.get("dynamic_tools")
    if isinstance(raw_dynamic, dict) and raw_dynamic:
        source = "state.dynamic_tools"
    else:
        source = "graph_closure_default_tools"
    default_keys = sorted((default_tools or {}).keys())
    state_dyn_keys = sorted(raw_dynamic.keys()) if isinstance(raw_dynamic, dict) else []
    effective_keys = sorted(available_tools.keys())
    breakdown = {name: _tool_kind_for_log(name, available_tools[name]) for name in effective_keys}
    logger.info(
        "planning_node: tools for planning — source=%s effective_count=%d effective_keys=%s "
        "state_dynamic_keys=%s default_closure_keys=%s kind_by_key=%s",
        source,
        len(effective_keys),
        effective_keys,
        state_dyn_keys,
        default_keys,
        breakdown,
    )


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
    """Plan todos using resolved planning context + optional DAG decomposition."""
    query_input = str(
        state.get("intent") or state.get("enriched_query") or state.get("user_query") or ""
    ).strip()
    if not query_input:
        return {"todos": [], "todo_md": "# TODOs\n\n- (empty)\n"}

    planning_context = await resolve_planning_context(
        state,
        query_input=query_input,
        gateway_context=gateway_context,
        default_prompts=default_prompts,
        default_tools=default_tools,
    )
    query_mode = str(planning_context.get("query_mode") or "analysis")
    intent_text = str(planning_context.get("intent") or query_input)
    target_tool = str(planning_context.get("target_tool") or "")
    raw_tool_params = planning_context.get("tool_params")
    tool_params = raw_tool_params if isinstance(raw_tool_params, dict) else {}
    available_tools = state.get("dynamic_tools") or default_tools or {}
    _log_planning_injected_tools(
        state=state,
        default_tools=default_tools,
        available_tools=cast(dict[str, Any], available_tools),
    )
    confirmed_terms = list(planning_context.get("confirmed_terms") or [])
    term_hints = list(planning_context.get("term_hints") or state.get("term_hints") or [])
    term_context = _merge_term_context(
        _build_term_context(confirmed_terms),
        _build_term_context_from_hints(term_hints),
    )
    planning_updates: dict[str, Any] = dict(planning_context)

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
            planning_updates["query_mode"] = "analysis"
            planning_updates["target_tool"] = ""
            target_tool = ""
        elif query_mode == "online_query" and is_delegate_tool:
            # Delegate tools should use the dedicated delegation path for gateway hand-off.
            query_mode = "agent_delegate"
            planning_updates["query_mode"] = "agent_delegate"
        elif query_mode == "agent_delegate" and not is_delegate_tool:
            # Non-delegate tools should run through direct tool invocation.
            query_mode = "online_query"
            planning_updates["query_mode"] = "online_query"

    plan: list[dict[str, Any]] = []
    if query_mode == "analysis" and not planning_updates.get("ambiguous_terms"):
        merged_state = cast(AgentState, {**state, **planning_updates})
        plan_updates = await decompose_analysis_plan(
            merged_state,
            intent=intent_text,
            gateway_context=gateway_context,
            default_prompts=default_prompts,
            default_tools=default_tools,
        )
        plan = list(plan_updates.get("plan", []) or [])
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
    todos = expand_relation_todos(todos)
    todo_md = _build_todo_md(todos)
    todo_md_path = _persist_todo_md(state.get("workspace_dir"), todo_md)
    plan_tasks = _plan_tasks_from_analysis_plan(plan)
    if not plan_tasks and target_tool:
        plan_tasks = [_direct_plan_task(todo_id="t_direct", goal=intent_text, tool=target_tool)]
    ensure_multitask_defaults(state)
    set_planned_tasks(state, plan_tasks)
    if plan_tasks:
        queue_order, blocked_reasons = _resolve_dependency_graph(plan_tasks)
    else:
        queue_order, blocked_reasons = ([], {})
    set_task_queue(state, queue_order)
    for task in plan_tasks:
        reason = blocked_reasons.get(task.todo_id)
        if reason:
            ensure_blocked_task(state, task, blocked_by=reason)
    logger.info(
        "planning_node: resolved tasks planned=%d queue_len=%d blocked=%s",
        len(plan_tasks),
        len(queue_order),
        list(blocked_reasons.keys()),
    )
    multitask_updates = {
        "planned_tasks": state.get("planned_tasks"),
        "task_queue": state.get("task_queue"),
        "results_list": state.get("results_list"),
        "results_map": state.get("results_map"),
    }

    return {
        **planning_updates,
        "plan": plan,
        "todos": todos,
        "todo_md": todo_md,
        "todo_md_path": todo_md_path,
        **multitask_updates,
    }
