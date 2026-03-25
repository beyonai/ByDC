"""Agent State definitions for the LangGraph orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph.message import MessagesState

if TYPE_CHECKING:
    from gateway_sdk import AgentContext


class AgentState(MessagesState):
    """The state dictionary for the core agent graph.

    Inherits ``messages`` from MessagesState.
    """

    # --- Gateway / Request Context ---
    agent_id: str | None
    agent_name: str | None
    workspace_dir: str | None
    # 由 worker 传入，节点用其 emit 思考事件；运行期为 AgentContext，声明为 Any 避免循环导入
    gateway_context: Any | None

    # --- Intent Analysis (Node 1) ---
    intent: str | None
    clarify_needed: bool
    # intent_node 检索到的知识原文（截断），供后续节点引用
    knowledge_preview: str | None

    # --- Planning (Node 2) ---
    plan: list[dict[str, Any]]

    # --- Execution / Results (Node 3) ---
    results: list[Any]
