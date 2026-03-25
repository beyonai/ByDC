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

    # --- Intent Analysis (Node 1) ---
    intent: str | None
    clarify_needed: bool

    # --- Planning (Node 2) ---
    plan: list[dict[str, Any]]

    # --- Execution / Results (Node 3) ---
    # Optional list or dict of results gathered so far
    results: list[Any]
