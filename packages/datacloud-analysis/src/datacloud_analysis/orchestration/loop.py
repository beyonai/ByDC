"""③ ReAct execution loop + state router (design §3.1).

Responsibilities
----------------
- Iterate over the DAG plan.
- For each task, call sandbox_executor.
- If it's a multi-task plan, intermediate results should be saved to Workspace.
- If it's a single task, results can be stored in state directly.
"""

from __future__ import annotations

import logging
from typing import Any
import os
import json
from pathlib import Path

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.orchestration.sandbox_executor import execute_next_task

logger = logging.getLogger(__name__)


async def loop_node(state: AgentState) -> dict:
    """Single iteration of the ReAct loop.

    Executes the next pending task in the plan.
    """
    plan = state.get("plan", [])
    results = state.get("results", [])
    workspace_dir = state.get("workspace_dir")
    
    pending = [t for t in plan if t.get("status") == "pending"]

    if not pending:
        logger.debug("loop_node: all tasks done, exiting loop.")
        return {}

    next_task = _pick_next_task(pending, plan)
    
    # Execute the task
    updated_task, output = await execute_next_task(next_task, state)
    
    # Save output
    is_multi_task = len(plan) > 1
    
    if is_multi_task and workspace_dir:
        # Write to workspace
        temp_dir = Path(workspace_dir) / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = temp_dir / f"{updated_task['id']}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False)
        logger.info("Saved intermediate result to %s", file_path)
        output_ref = {"task_id": updated_task['id'], "file_path": str(file_path)}
        results.append(output_ref)
    else:
        # Single task, keep in memory
        results.append({"task_id": updated_task['id'], "data": output})

    # Update plan
    updated_plan = [updated_task if t["id"] == updated_task["id"] else t for t in plan]
    
    return {"plan": updated_plan, "results": results}


def _pick_next_task(
    pending: list[dict[str, Any]],
    all_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select the next executable task."""
    done_ids = {t["id"] for t in all_tasks if t.get("status") == "done"}
    for task in pending:
        deps = task.get("deps", [])
        if all(d in done_ids for d in deps):
            return task
    return pending[0]
