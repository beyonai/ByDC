"""Stream the analysis graph for programmatic / embedded callers (non-Gateway).

Use this when you have resolved ``TaskPaths`` and a LangGraph ``run_config``
(``thread_id``, metadata) and want ``stream_mode="values"`` updates. Gateway
workers typically call ``create_agent().astream_events`` instead.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from datacloud_analysis.orchestration.graph_builder import build_analysis_graph
from datacloud_analysis.orchestration.graph_compile_policy import compile_graph_with_policy

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
    compiled = compile_graph_with_policy(graph, caller_name="run_agent")

    workspace_dir = str(task_paths.inputs.parent)

    if isinstance(user_message, Command):
        input_payload: Any = user_message
    else:
        input_payload = {
            "messages": [HumanMessage(content=str(user_message))],
            "agent_id": None,
            "agent_name": None,
            "workspace_dir": workspace_dir,
            "user_query": "",
            "enriched_query": "",
            "knowledge_payload": {},
            "term_hints": [],
            "knowledge_snippets": [],
            "thinking_log": {},
            "planning_input_source": "",
            "plan": [],
            "todos": [],
            "todo_md": "",
            "todo_md_path": "",
            "intent": None,
            "clarify_needed": False,
            "results": [],
            "execution_status": "",
            "todo_active_id": "",
            "todo_tool_plan": [],
            "active_tools": [],
            "execution_trace": [],
            "invocation_dedup": [],
            "final_answer": "",
            "artifact_refs": [],
            "execution_summary": None,
            "execution_summary_persistence": None,
            "resume_context": {},
            "query_mode": "analysis",
            "chitchat_reply": None,
            "target_tool": "",
            "tool_params": {},
            "concept_terms": [],
            "confirmed_terms": [],
            "ambiguous_terms": [],
            "session_alias_map": {},
            "dynamic_tools": {},
            "prompts_overwrite": {},
            "planned_tasks": [],
            "task_queue": [],
            "results_list": [],
            "results_map": {},
            "final_summary": {},
        }

    async for event in compiled.astream(
        input_payload,
        config=cast(RunnableConfig, run_config),
        stream_mode="values",
    ):
        yield event
