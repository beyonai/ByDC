"""③ ReAct execution loop + state router + HITL (design §3.1 LOOP_REGION).

This node implements the ``CHECKER → DO_TASK / HITL_NODE`` cycle:

- Inspect the current state to decide:
  * All sub-tasks done   → exit loop (fall-through to insight_node)
  * Sub-task pending     → call ``sandbox_executor`` (DO_TASK path)
  * High-risk / ambiguous → call LangGraph ``interrupt()`` (HITL path)

HITL mechanism
--------------
When the Agent encounters ambiguity it calls LangGraph's native
``interrupt(value)`` function.  LangGraph freezes the current state into
a checkpoint and raises ``GraphInterrupt``.  The message handler catches this,
records the checkpoint_id, and emits a callback event to the task
scheduler so the frontend can show a user-facing confirmation card.

Resume path
-----------
The message handler re-enters the compiled graph via ``Command(resume=user_answer)``
using the same ``thread_id``.  LangGraph restores the checkpoint and
continues execution from the interrupted node.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import interrupt

from datacloud_analysis.orchestration.sandbox_executor import execute_next_task

logger = logging.getLogger(__name__)

# Tasks that require explicit user confirmation before execution.
_HIGH_RISK_TASK_TYPES = {"delete_data", "bulk_write", "schema_change"}


async def loop_node(state: dict[str, Any]) -> dict[str, Any]:
    """Single iteration of the ReAct loop.

    LangGraph will call this node repeatedly (via a self-edge) until it
    signals completion by *not* adding a self-transition.

    Current simplified logic:
    - If the DAG has pending tasks, execute the next one.
    - If a pending task is high-risk, interrupt and ask the user.
    - If no pending tasks remain, return state unchanged (falls through to insight).

    TODO: replace with full ReAct reasoning using the reasoning LLM.
    """
    dag: list[dict[str, Any]] = state.get("dag", [])
    pending = [t for t in dag if t.get("status") != "done"]

    if not pending:
        logger.debug("loop_node: all tasks done, exiting loop.")
        return state

    next_task = _pick_next_task(pending, dag)

    # HITL path — pause and ask the user.
    if next_task.get("type") in _HIGH_RISK_TASK_TYPES:
        logger.info("loop_node: high-risk task detected, triggering HITL interrupt.")
        user_answer = interrupt(
            {
                "question": f"Task '{next_task['id']}' ({next_task['type']}) may be destructive. Proceed?",
                "options": ["yes", "no"],
                "task_id": next_task["id"],
            }
        )
        if user_answer != "yes":
            next_task["status"] = "skipped"
            return state

    # Normal execution path.
    updated_task = await execute_next_task(next_task, state)
    # Merge updated task back into the DAG.
    state["dag"] = [updated_task if t["id"] == updated_task["id"] else t for t in dag]
    return state


def _pick_next_task(
    pending: list[dict[str, Any]],
    all_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select the next executable task (all deps satisfied)."""
    done_ids = {t["id"] for t in all_tasks if t.get("status") == "done"}
    for task in pending:
        deps = task.get("deps", [])
        if all(d in done_ids for d in deps):
            return task
    return pending[0]  # fallback: pick first pending
