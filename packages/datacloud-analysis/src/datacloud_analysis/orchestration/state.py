"""Agent State definitions for the LangGraph orchestrator."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from langgraph.graph.message import MessagesState

from datacloud_analysis.orchestration.shared.contracts import PlanTask, TaskResult


class AgentState(MessagesState):
    """State dictionary for the DataCloud 5-node orchestration graph."""

    # --- Gateway / request context ---
    agent_id: str | None
    agent_name: str | None
    workspace_dir: str | None

    # --- Core query context ---
    user_query: str | None
    enriched_query: str | None
    enriched_query_source: str | None
    enriched_query_confidence: float | None
    intent: str | None
    knowledge_payload: dict[str, Any] | None
    term_hints: list[dict[str, Any]] | None
    knowledge_snippets: list[dict[str, Any]] | None
    thinking_log: dict[str, Any] | None
    planning_input_source: str | None

    # --- Intent + routing ---
    clarify_needed: bool
    query_mode: str | None
    chitchat_reply: str | None
    target_tool: str | None
    tool_params: dict[str, Any] | None

    # --- Term disambiguation ---
    concept_terms: list[str] | None
    confirmed_terms: list[dict[str, Any]] | None
    ambiguous_terms: list[dict[str, Any]] | None
    session_alias_map: dict[str, str] | None

    # --- Planning output ---
    plan: list[dict[str, Any]]
    todos: list[dict[str, Any]] | None
    todo_md: str | None
    todo_md_path: str | None

    # --- Execution runtime ---
    execution_status: str | None
    todo_active_id: str | None
    todo_tool_plan: list[dict[str, Any]] | None
    active_tools: list[str] | None
    execution_trace: list[dict[str, Any]] | None
    invocation_dedup: list[str] | None

    # --- Results / finalization ---
    results: list[Any]
    final_answer: str | None
    artifact_refs: list[dict[str, Any]] | None
    execution_summary: dict[str, Any] | None
    execution_summary_persistence: dict[str, Any] | None
    execution_summary_ref: dict[str, Any] | None
    resume_context: dict[str, Any] | None

    # Optional; should not be persisted with callable objects in checkpoint.
    prompts_overwrite: dict[str, Any] | None
    dynamic_tools: dict[str, Any] | None
    planned_tasks: list[dict[str, Any]] | None
    task_queue: list[str] | None
    results_list: list[dict[str, Any]] | None
    results_map: dict[str, dict[str, Any]] | None
    final_summary: dict[str, Any] | None

    # --- 重构新增字段 (P8) ---
    intent_source: str | None  # "command" | "react" | "chitchat"
    command_result: dict | None  # intend 节点命令结果
    react_rounds: int | None  # 实际执行轮数
    react_final: dict | None  # 停止时的结构化结果
    react_checkpoint: dict | None  # React loop checkpoint for interrupt/resume（delegate 工具路径）

    # --- react_loop interrupt/resume State 持久化（方案 B）---
    # interrupt 时由 react_loop 写入，LangGraph checkpoint 自动持久化；resume 时读出并清除。
    react_messages: list[dict[str, Any]] | None  # 中断时的消息历史（序列化为 dict 列表）
    react_pending_tool_calls: list[dict[str, Any]] | None  # 中断时未执行的 tool calls
    react_round_idx: int | None  # 中断时的 round 索引
    react_last_query_data: dict[str, Any] | None  # 中断时缓存的 query data block
    answer_streamed: bool | None  # llm_call_node 是否已流式输出 answer

    # --- 澄清插件 interrupt/resume 缓存（方案 A）---
    # interrupt 前写入，resume 后 format 完成时清除，避免 _analyze_clarification 被重复调用。
    _clarification_cache: dict[str, Any] | None

    # --- V0.3 Tool-as-Node：阶段 1 ReAct 内部消息日志 ---
    # llm_call_node 每轮追加 AIMessage（序列化），tool_dispatcher_node 追加 ToolMessage。
    # 通过正常 return 提交 → LangGraph checkpoint 自动持久化。
    # interrupt() 重跑 tool_dispatcher_node 时从 checkpoint 读取，不重调 LLM。
    react_messages_log: list[dict[str, Any]] | None

    # --- V0.3 Tool-as-Node：阶段 2 澄清子流程状态 ---
    pending_clarification_context: dict[str, Any] | None
    clarification_analyze_result: dict[str, Any] | None
    clarification_formatted_params: dict[str, Any] | None


StateDict = MutableMapping[str, Any]


def ensure_multitask_defaults(state: StateDict) -> None:
    """Initialize empty containers for multi-task context keys."""
    if not isinstance(state.get("planned_tasks"), list):
        state["planned_tasks"] = []
    if not isinstance(state.get("task_queue"), list):
        state["task_queue"] = []
    if not isinstance(state.get("results_list"), list):
        state["results_list"] = []
    raw_map = state.get("results_map")
    if not isinstance(raw_map, dict):
        state["results_map"] = {}
    else:
        sanitized: dict[str, dict[str, Any]] = {}
        for key, value in raw_map.items():
            key_str = str(key).strip()
            if not key_str:
                continue
            if isinstance(value, Mapping):
                sanitized[key_str] = dict(value)
        state["results_map"] = sanitized


def set_planned_tasks(state: StateDict, tasks: Sequence[PlanTask]) -> None:
    ensure_multitask_defaults(state)
    state["planned_tasks"] = [task.to_dict() for task in tasks]


def get_planned_tasks(state: Mapping[str, Any]) -> list[PlanTask]:
    raw = state.get("planned_tasks") or []
    tasks: list[PlanTask] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, Mapping):
                try:
                    tasks.append(PlanTask.from_dict(entry))
                except ValueError:
                    continue
    return tasks


def set_task_queue(state: StateDict, queue: Sequence[str]) -> None:
    ensure_multitask_defaults(state)
    normalized = [str(item).strip() for item in queue if str(item).strip()]
    state["task_queue"] = normalized


def get_task_queue(state: Mapping[str, Any]) -> list[str]:
    raw = state.get("task_queue") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def upsert_task_result(state: StateDict, result: TaskResult) -> None:
    """Insert or replace a TaskResult in both list/map containers."""
    ensure_multitask_defaults(state)
    serialized = result.to_dict()
    results_list = state["results_list"]
    assert isinstance(results_list, list)
    replaced = False
    for idx, entry in enumerate(results_list):
        if isinstance(entry, Mapping) and str(entry.get("todo_id")) == result.todo_id:
            results_list[idx] = serialized
            replaced = True
            break
    if not replaced:
        results_list.append(serialized)
    results_map = state["results_map"]
    assert isinstance(results_map, dict)
    results_map[result.todo_id] = serialized


def get_task_results(state: Mapping[str, Any]) -> list[TaskResult]:
    raw = state.get("results_list") or []
    results: list[TaskResult] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, Mapping):
                try:
                    results.append(TaskResult.from_dict(entry))
                except ValueError:
                    continue
    return results


def get_task_result_map(state: Mapping[str, Any]) -> dict[str, TaskResult]:
    raw_map = state.get("results_map")
    task_map: dict[str, TaskResult] = {}
    if not isinstance(raw_map, Mapping):
        return task_map
    for key, entry in raw_map.items():
        key_str = str(key).strip()
        if not key_str or not isinstance(entry, Mapping):
            continue
        try:
            task_map[key_str] = TaskResult.from_dict(entry)
        except ValueError:
            continue
    return task_map


def ensure_blocked_task(
    state: StateDict,
    task: PlanTask,
    *,
    blocked_by: str = "missing_dependency",
) -> None:
    """Prefill a blocked TaskResult for downstream consumers."""
    blocked_result = TaskResult(
        todo_id=task.todo_id,
        status="blocked",
        result_meta={},
        artifact_refs=[],
        blocked_by=blocked_by,
    )
    upsert_task_result(state, blocked_result)
