"""Agent State definitions for the LangGraph orchestrator."""

from __future__ import annotations

from typing import Any

from langgraph.graph.message import MessagesState


class AgentState(MessagesState):
    """The state dictionary for the core agent graph.

    Inherits ``messages`` from MessagesState.
    """

    # --- Gateway / Request Context ---
    agent_id: str | None
    agent_name: str | None
    workspace_dir: str | None
    # gateway_context は state に含めない — PG checkpointer がシリアライズできない。
    # worker は config["configurable"]["gateway_context"] に格納し、
    # graph_builder クロージャが各ノードへ明示的に渡す。

    # --- Intent Analysis (Node 1) ---
    intent: str | None
    clarify_needed: bool
    # intent_node 检索到的知识原文（截断），供后续节点引用
    knowledge_preview: str | None
    # 在线查数快捷路径：online_query 走 direct_tool；否则 analysis 走 dag
    query_mode: str | None
    target_tool: str | None
    tool_params: dict[str, Any] | None

    # --- Planning (Node 2) ---
    plan: list[dict[str, Any]]

    # --- Execution / Results (Node 3) ---
    results: list[Any]
    # Optional; Gateway+checkpointer 路径应留空，由 graph.compile 闭包注入，避免工具 callable 无法序列化。
    prompts_overwrite: dict[str, Any] | None
    dynamic_tools: dict[str, Any] | None
