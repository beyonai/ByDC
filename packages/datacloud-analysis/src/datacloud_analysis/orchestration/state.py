"""Agent State definitions for the LangGraph orchestrator."""

from __future__ import annotations

from typing import Any

from langgraph.graph.message import MessagesState


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
    knowledge_preview: str | None
    knowledge_payload: dict[str, Any] | None
    term_hints: list[dict[str, Any]] | None
    knowledge_snippets: list[dict[str, Any]] | None

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
    resume_context: dict[str, Any] | None

    # Optional; should not be persisted with callable objects in checkpoint.
    prompts_overwrite: dict[str, Any] | None
    dynamic_tools: dict[str, Any] | None
