"""Stream the analysis graph for programmatic / embedded callers (non-Gateway).

Use this when you have resolved ``TaskPaths`` and a LangGraph ``run_config``
(``thread_id``, metadata) and want ``stream_mode="values"`` updates. Gateway
workers typically call ``create_agent().astream_events`` instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

if TYPE_CHECKING:
    from datacloud_analysis.workspace.paths import TaskPaths

logger = logging.getLogger(__name__)


async def run_agent(
    user_message: Any,
    task_paths: TaskPaths,
    run_config: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Compile the analysis graph and stream partial state dicts.

    Uses ``get_checkpointer()`` when ``session.checkpointer.set_checkpointer``
    has been configured; otherwise compiles without checkpointing.

    Args:
        user_message: Plain text or ``Command(resume=...)`` for HITL resume.
        task_paths: Per-task workspace directories from ``build_task_paths``.
        run_config: LangGraph runnable config (``configurable.thread_id``, etc.).

    Yields:
        State snapshots from ``astream(..., stream_mode="values")``.
    """
    graph = build_analysis_graph()
    try:
        from datacloud_analysis.session.checkpointer import get_checkpointer  # noqa: PLC0415

        compiled = graph.compile(checkpointer=get_checkpointer())
    except RuntimeError:
        logger.warning(
            "run_agent: checkpointer not initialized — compiling graph without checkpointing."
        )
        compiled = graph.compile()

    workspace_dir = str(task_paths.inputs.parent)

    if isinstance(user_message, Command):
        input_payload: Any = user_message
    else:
        input_payload = {
            "messages": [HumanMessage(content=str(user_message))],
            "agent_id": None,
            "agent_name": None,
            "workspace_dir": workspace_dir,
            "plan": [],
            "intent": None,
            "clarify_needed": False,
            "results": [],
            "query_mode": "analysis",
            "chitchat_reply": None,
            "target_tool": "",
            "tool_params": {},
            "dynamic_tools": {},
            "prompts_overwrite": {},
        }

    async for event in compiled.astream(
        input_payload,
        config=run_config,
        stream_mode="values",
    ):
        yield event
