"""① Intent parsing — workflow first node (design §3.1 PRE_KNOW).

Responsibilities
----------------
- Load short-term memory context from the checkpointer (conversation history).
- Fetch ``global_rules`` from long-term memory and mount ``MEMORY.md``.
- Call the *quick* LLM to classify intent and attach 1-hop knowledge snippets.
- Pass the enriched state to the DAG planner.

This module also exposes ``run_agent()``, the top-level coroutine called by
``gateway.handler.MessageHandler``.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from datacloud_agent.workspace.paths import TaskPaths

logger = logging.getLogger(__name__)


async def run_agent(
    user_message: Any,
    task_paths: TaskPaths,
    run_config: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Top-level Agent runner.  Builds and streams the LangGraph graph.

    Args:
        user_message: The user's question string, or a LangGraph ``Command``
                      object when resuming from an HITL interrupt.
        task_paths:   Resolved file-system paths for this task.
        run_config:   LangGraph config dict (thread_id + metadata).

    Yields:
        LangGraph stream events.
    """
    from datacloud_agent.session.checkpointer import get_checkpointer  # noqa: PLC0415

    graph = _build_graph(task_paths)
    checkpointer = get_checkpointer()
    compiled = graph.compile(checkpointer=checkpointer)

    async for event in compiled.astream(
        {"messages": [{"role": "user", "content": user_message}]},
        config=run_config,
        stream_mode="values",
    ):
        yield event


def _build_graph(task_paths: TaskPaths) -> Any:
    """Assemble the LangGraph StateGraph for one task.

    Node wiring (design §3.1):
        START → intent_node → dag_node → loop_node → insight_node → END
    """
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415
    from langgraph.graph.message import MessagesState  # noqa: PLC0415

    from datacloud_agent.orchestration.dag import dag_node  # noqa: PLC0415
    from datacloud_agent.orchestration.insight import insight_node  # noqa: PLC0415
    from datacloud_agent.orchestration.loop import loop_node  # noqa: PLC0415

    builder = StateGraph(MessagesState)
    builder.add_node("intent", _intent_node)
    builder.add_node("dag", dag_node)
    builder.add_node("loop", loop_node)
    builder.add_node("insight", insight_node)

    builder.add_edge(START, "intent")
    builder.add_edge("intent", "dag")
    builder.add_edge("dag", "loop")
    builder.add_edge("loop", "insight")
    builder.add_edge("insight", END)

    return builder


async def _intent_node(state: dict[str, Any]) -> dict[str, Any]:
    """Classify intent and attach short-term + global memory context.

    TODO: implement with quick LLM call and memory loader.
    """
    logger.debug("intent_node: classifying intent …")
    return state
