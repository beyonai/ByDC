"""③ ReAct execution loop + state router (design §3.1).

Responsibilities
----------------
- Iterate over the DAG plan.
- For each round, collect ALL ready tasks (deps satisfied) and execute them concurrently.
- If it's a multi-task plan, intermediate results should be saved to Workspace.
- If it's a single task, results can be stored in state directly.
- Emit a REASONING_LOG_DELTA thinking event after each task completes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseReasonMessageType

from datacloud_analysis.orchestration.sandbox_executor import execute_next_task
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def loop_node(state: AgentState) -> dict:
    """One round of the ReAct loop.

    Executes ALL currently-ready tasks (deps satisfied) concurrently,
    then returns updated plan + results so the router can decide whether
    to loop again or proceed to insight.
    """
    plan = state.get("plan", [])
    results = list(state.get("results", []))  # copy — LangGraph merges via reducer
    workspace_dir = state.get("workspace_dir")

    pending = [t for t in plan if t.get("status") == "pending"]
    if not pending:
        logger.debug("loop_node: no pending tasks, exiting loop.")
        return {}

    # Collect every task whose deps are already done → run them all at once
    ready_tasks = _pick_ready_tasks(pending, plan)
    is_multi_task = len(plan) > 1

    logger.info(
        "loop_node: executing %d ready task(s) concurrently: %s",
        len(ready_tasks),
        [t["id"] for t in ready_tasks],
    )

    # Concurrent execution
    task_outputs: list[tuple[dict, Any]] = await asyncio.gather(
        *[execute_next_task(t, state) for t in ready_tasks]
    )

    updated_plan = list(plan)
    context = state.get("gateway_context")

    for updated_task, output in task_outputs:
        # ── Persist output ──────────────────────────────────────────────
        if is_multi_task and workspace_dir:
            temp_dir = Path(workspace_dir) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            file_path = temp_dir / f"{updated_task['id']}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False)
            logger.info("Saved intermediate result to %s", file_path)
            results.append({"task_id": updated_task["id"], "file_path": str(file_path)})
        else:
            results.append({"task_id": updated_task["id"], "data": output})

        # ── Update plan ─────────────────────────────────────────────────
        updated_plan = [
            updated_task if t["id"] == updated_task["id"] else t
            for t in updated_plan
        ]

        # ── Push thinking event ─────────────────────────────────────────
        if context is not None:
            total = len(updated_plan)
            done_count = sum(
                1 for t in updated_plan if t.get("status") in ("done", "failed")
            )
            status_icon = "✓" if updated_task.get("status") == "done" else "✗"
            output_preview = str(output)[:300] if output else "（无结果）"
            thinking = (
                f"[{status_icon} {done_count}/{total}] {updated_task['id']}："
                f"{updated_task.get('description', '')}\n"
                f"结果摘要：{output_preview}"
            )
            await context.emit_chunk(
                StreamChunkEvent(content="执行任务"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_title.value,
            )
            await context.emit_chunk(
                StreamChunkEvent(content=thinking),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_text.value,
            )

    return {"plan": updated_plan, "results": results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_ready_tasks(
    pending: list[dict[str, Any]],
    all_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every pending task whose dependencies are all done.

    Falls back to the first pending task if nothing is ready yet
    (should not happen with a well-formed DAG, but avoids deadlock).
    """
    done_ids = {t["id"] for t in all_tasks if t.get("status") == "done"}
    ready = [
        t for t in pending
        if all(d in done_ids for d in t.get("deps", []))
    ]
    return ready if ready else [pending[0]]
