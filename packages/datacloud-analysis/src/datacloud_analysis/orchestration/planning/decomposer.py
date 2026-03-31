"""Analysis-plan decomposition for planning node (legacy DAG-free)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, cast

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

_EXCLUDED_PLANNING_TOOLS: frozenset[str] = frozenset({"search_knowledge"})
_SANDBOX_BUILTIN_PLAN_TYPES: frozenset[str] = frozenset(
    {
        "build_skill",
        "code_exec",
        "file_read",
        "file_write",
        "recall_memory",
        "render_report",
    }
)
_PLANNER_STATIC_SYSTEM = """你是一个任务规划专家。请将分析目标拆解为具体子任务。\
如果单次数据查询即可解答，只输出一个子任务。

## 支持的任务类型

| type | 使用场景 |
|------|---------|
| [来自本轮 HumanMessage 的可用动态工具名] | 向挂载的外部服务查询原始数据，将其本身作为 type 名并根据工具要求在 params 中提供请求参数 |
| code_exec | 对已查询到的数据文件进行计算/统计/关联分析，必须有 deps，须在 params.code 中提供 Python 代码 |
| render_report | 生成报告 |

## 判断规则（重要）

- 问候、寒暄、感谢等与数据分析无关的闲聊：不应由本节点处理（上游应路由为 chitchat）；若仍进入本节点，禁止单独规划仅有 render_report 的任务
- render_report 仅用于在已有查询或 code_exec 结果之后组装最终报告，且不得作为全 plan 中唯一任务，除非前置任务已提供可引用的数据摘要
- 任务需要"从系统查询/获取数据" -> 必须从【可用动态工具】列表中挑选动作作为 type，deps 可为空
- 任务是"基于已查结果进行统计/汇总/计算/关联"且有前置任务 -> 必须使用 code_exec，不得使用查询工具
- deps 为空的任务禁止使用 code_exec
- 对于任何 `*_query` 类型任务，`params` 里必须包含 `query`（或 `question`），禁止返回空 `params`

## code_exec 的 Python 代码约定

- 变量 `input_files` 已注入，类型为 dict，key = 前置任务 id，value = JSONL 文件绝对路径
- JSONL 格式：第一行是 meta（含 columns、total 字段），后续每行是一条数据记录
- 可直接使用 `pandas`（as pd）和 `json` 模块，无需 import（已预置）
- 将最终计算结果赋值给 `_result` 变量（类型为 list[dict] 或 dict）
- 同时用 print() 输出关键结果摘要

## 返回格式

返回严格的 JSON 数组，每个元素包含：
- "id": 任务ID（如 t1、t2）
- "type": 任务类型
- "description": 任务描述
- "status": "pending"
- "deps": 依赖的前置任务ID列表
- "params": 执行所需的参数对象
"""


def _planning_tools_view(dynamic_tools: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in dynamic_tools.items() if k not in _EXCLUDED_PLANNING_TOOLS}


def _relation_semantic_types(todo: dict[str, Any]) -> set[str]:
    raw_term_context = todo.get("term_context")
    semantic_types: set[str] = set()
    if isinstance(raw_term_context, dict):
        raw_semantic_types = raw_term_context.get("semantic_types")
        if isinstance(raw_semantic_types, list):
            semantic_types.update(str(item).strip().lower() for item in raw_semantic_types if str(item).strip())
        return semantic_types

    if isinstance(raw_term_context, list):
        for item in raw_term_context:
            if not isinstance(item, dict):
                continue
            semantic_type = str(item.get("semantic_type") or "").strip().lower()
            if semantic_type:
                semantic_types.add(semantic_type)
    return semantic_types


def _should_split_relation_todo(todo: dict[str, Any]) -> bool:
    """Return True when a relation todo should be expanded into locate + query."""
    semantic_types = _relation_semantic_types(todo)
    if "relation" not in semantic_types:
        return False
    return not todo.get("depends_on")


def split_relation_todo(todo: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one relation todo into locate subject/object + query relation steps."""
    todo_id = str(todo.get("todo_id") or "t_rel").strip() or "t_rel"
    goal = str(todo.get("goal") or "")
    status = str(todo.get("status") or "pending")
    term_context = todo.get("term_context")
    relation_inputs = dict(todo.get("inputs") or {}) if isinstance(todo.get("inputs"), dict) else {}

    locate_todo = {
        "todo_id": f"{todo_id}_locate",
        "goal": f"定位「{goal}」中的主语和宾语实体",
        "required_tools": ["search_knowledge"],
        "blocked_tools": [],
        "required_capabilities": [{"capability_id": "search_knowledge", "capability_type": "tool"}],
        "blocked_capabilities": [],
        "inputs": {"query": goal},
        "depends_on": [],
        "term_context": term_context,
        "acceptance_criteria": f"task {todo_id}_locate executed successfully",
        "status": status,
    }
    query_todo = {
        "todo_id": f"{todo_id}_query",
        "goal": goal,
        "required_tools": list(todo.get("required_tools") or []),
        "blocked_tools": list(todo.get("blocked_tools") or []),
        "required_capabilities": list(todo.get("required_capabilities") or []),
        "blocked_capabilities": list(todo.get("blocked_capabilities") or []),
        "inputs": relation_inputs,
        "depends_on": [f"{todo_id}_locate"],
        "param_from_deps": {f"{todo_id}_locate": ["subject_id", "object_id"]},
        "term_context": term_context,
        "acceptance_criteria": str(
            todo.get("acceptance_criteria") or f"task {todo_id}_query executed successfully"
        ),
        "status": status,
    }
    return [locate_todo, query_todo]


def _unique_todo_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _rewrite_relation_split_ids(split_todos: list[dict[str, Any]], used_ids: set[str]) -> list[dict[str, Any]]:
    if len(split_todos) != 2:
        return split_todos
    locate = dict(split_todos[0])
    query = dict(split_todos[1])

    locate_id = _unique_todo_id(str(locate.get("todo_id") or "t_rel_locate"), used_ids)
    query_id = _unique_todo_id(str(query.get("todo_id") or "t_rel_query"), used_ids)

    query_param_from_deps = dict(query.get("param_from_deps") or {})
    source_dep_ids = list(query_param_from_deps.keys())
    source_dep_id = source_dep_ids[0] if source_dep_ids else ""
    dep_fields = list(query_param_from_deps.get(source_dep_id) or ["subject_id", "object_id"])

    locate["todo_id"] = locate_id
    query["todo_id"] = query_id
    query["depends_on"] = [locate_id]
    query["param_from_deps"] = {locate_id: dep_fields}
    return [locate, query]


def expand_relation_todos(raw_todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand relation todos to two-step orchestration when applicable."""
    expanded: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for todo in raw_todos:
        todo_id = str(todo.get("todo_id") or "").strip()
        if todo_id:
            used_ids.add(todo_id)

    for todo in raw_todos:
        if not _should_split_relation_todo(todo):
            expanded.append(todo)
            continue
        split_todos = split_relation_todo(todo)
        rewritten = _rewrite_relation_split_ids(split_todos, used_ids)
        expanded.extend(rewritten)
    return expanded


def _normalize_query_params(plan: list[dict[str, object]], intent: str) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for task in plan:
        if not isinstance(task, dict):
            continue
        task_type = str(task.get("type", ""))
        params_raw = task.get("params", {})
        params = dict(params_raw) if isinstance(params_raw, dict) else {}
        description = str(task.get("description", "") or "")
        fallback_text = description or intent
        if task_type.endswith("_query") and not params.get("query") and not params.get("question"):
            params["query"] = fallback_text
        normalized.append({**task, "params": params})
    return normalized


def _strip_excluded_tasks_from_plan(
    plan: list[dict[str, object]], excluded_types: frozenset[str]
) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    for task in plan:
        if not isinstance(task, dict):
            continue
        if str(task.get("type", "")) in excluded_types:
            continue
        kept.append(dict(task))
    kept_ids = {str(t.get("id", "")) for t in kept if t.get("id") is not None}
    repaired: list[dict[str, object]] = []
    for task in kept:
        deps = task.get("deps", [])
        if isinstance(deps, list):
            task["deps"] = [d for d in deps if str(d) in kept_ids]
        repaired.append(task)
    return repaired


def _log_planned_type_mismatches(
    plan: list[dict[str, object]],
    planning_tools: dict[str, object],
    full_dynamic_tools: dict[str, object],
) -> None:
    allowed = set(planning_tools.keys()) | set(_SANDBOX_BUILTIN_PLAN_TYPES)
    full_keys = sorted(full_dynamic_tools.keys())
    planner_keys = sorted(planning_tools.keys())
    logger.info(
        "planning_decomposer: dynamic_tools=%s planner_visible_tools=%s",
        full_keys,
        planner_keys,
    )
    for t in plan:
        if not isinstance(t, dict):
            continue
        task_type = str(t.get("type", ""))
        if task_type and task_type not in allowed:
            logger.warning(
                "planning_decomposer: task type mismatch task_id=%s type=%s planner_visible=%s",
                t.get("id"),
                task_type,
                planner_keys,
            )


async def _emit_planning_reasoning(
    *,
    gateway_context: Any,
    plan: list[dict[str, object]],
) -> None:
    if gateway_context is None:
        return
    task_lines = "\n".join(
        f"■ {task.get('id', '?')}（{task.get('type', 'unknown')}）：{task.get('description', '')}"
        for task in plan
        if isinstance(task, dict)
    )
    thinking = f"已将问题拆解为 {len(plan)} 个子任务：\n{task_lines}"
    await gateway_context.emit_chunk(
        StreamChunkEvent(content="任务规划"),
        event_type=EventType.REASONING_LOG_DELTA.value,
        content_type=SseReasonMessageType.think_title.value,
    )
    await gateway_context.emit_chunk(
        StreamChunkEvent(content=thinking),
        event_type=EventType.REASONING_LOG_DELTA.value,
        content_type=SseReasonMessageType.think_text.value,
    )


async def decompose_analysis_plan(
    state: AgentState,
    *,
    intent: str,
    gateway_context: Any = None,
    default_prompts: dict[str, Any] | None = None,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{\"plan\": [...]}`` for analysis-mode planning."""
    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    planning_tools = _planning_tools_view(cast(dict[str, object], dynamic_tools))
    tools_line = ", ".join(sorted(planning_tools.keys())) if planning_tools else "（无动态工具）"

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"
    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    static_sys = prompts_overwrite.get(
        "planning_system_prompt",
        prompts_overwrite.get(
            "planning_prompt",
            prompts_overwrite.get(
                "dag_system_prompt",
                prompts_overwrite.get("dag_prompt", _PLANNER_STATIC_SYSTEM),
            ),
        ),
    )
    dynamic_human = HumanMessage(
        content=(
            f"【可用动态工具列表】：{tools_line}\n\n"
            f"【需要分析的目标】：{intent}\n\n"
            "请输出 JSON 任务数组。"
        )
    )

    try:
        response = await llm.ainvoke([SystemMessage(content=static_sys), dynamic_human])
        content = cast(str, response.content)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        plan_raw = json.loads(content)
        plan = plan_raw if isinstance(plan_raw, list) else []
        plan = _normalize_query_params(plan, intent=intent)
        plan = _strip_excluded_tasks_from_plan(plan, _EXCLUDED_PLANNING_TOOLS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("planning_decomposer: plan generation failed, fallback to single step: %s", exc)
        plan = []

    if not plan and planning_tools:
        fallback_tool = sorted(planning_tools.keys())[0]
        plan = [
            {
                "id": "t1",
                "type": fallback_tool,
                "description": intent,
                "status": "pending",
                "deps": [],
                "params": {"query": intent},
            }
        ]
        plan = _normalize_query_params(plan, intent=intent)
    elif not plan and not planning_tools:
        return {
            "plan": [],
            "clarify_needed": True,
            "intent": "当前未配置可用的数据查询工具，请先完成 Agent 资源挂载。",
        }

    _log_planned_type_mismatches(
        cast(list[dict[str, object]], plan),
        planning_tools,
        cast(dict[str, object], dynamic_tools),
    )
    await _emit_planning_reasoning(
        gateway_context=gateway_context,
        plan=cast(list[dict[str, object]], plan),
    )
    return {"plan": plan}

