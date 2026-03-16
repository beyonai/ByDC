"""Sandbox task dispatcher (design §3.1 DO_TASK / TOOLBOX).

This module maps a sub-task type to the corresponding tool function and
runs it inside the current sandbox context.

Sub-task types → tools
----------------------
data_query      → tools.data.data_query
code_exec       → tools.sandbox.sbx_run_code
file_read       → tools.sandbox.sbx_read_file
file_write      → tools.sandbox.sbx_write_file
search_knowledge→ tools.knowledge.search_knowledge
recall_memory   → memory.tools.recall_memory
build_skill     → tools.skill.build_skill
render_report   → tools.report.render_report
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Registry: task type → callable (populated lazily to avoid circular imports)
_TASK_DISPATCHERS: dict[str, Any] = {}


async def execute_next_task(
    task: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Execute one sub-task and return the updated task dict.

    Args:
        task:  Sub-task dict from the DAG (must have ``id`` and ``type``).
        state: Current graph state (for context / message history).

    Returns:
        The task dict with ``status`` set to ``"done"`` or ``"failed"``
        and an ``output`` key containing the tool result.
    """
    task_type: str = task.get("type", "unknown")
    dispatcher = _get_dispatcher(task_type)

    if dispatcher is None:
        logger.warning("No dispatcher for task type '%s'; marking as failed.", task_type)
        return {**task, "status": "failed", "output": f"Unknown task type: {task_type}"}

    try:
        logger.debug("Executing task %s (type=%s) …", task["id"], task_type)
        output = await dispatcher(task.get("params", {}), state)
        return {**task, "status": "done", "output": output}
    except Exception as exc:  # noqa: BLE001
        logger.error("Task %s failed: %s", task["id"], exc)
        return {**task, "status": "failed", "output": str(exc)}


def _get_dispatcher(task_type: str) -> Any | None:
    """Return the async callable for the given task type (lazy import)."""
    if not _TASK_DISPATCHERS:
        _register_dispatchers()
    return _TASK_DISPATCHERS.get(task_type)


def _register_dispatchers() -> None:
    """Populate the dispatcher registry (called once on first use)."""
    try:
        from datacloud_analysis.tools.data import data_query  # noqa: PLC0415
        from datacloud_analysis.tools.knowledge import search_knowledge  # noqa: PLC0415
        from datacloud_analysis.tools.report import render_report  # noqa: PLC0415
        from datacloud_analysis.tools.sandbox import sbx_read_file, sbx_run_code, sbx_write_file  # noqa: PLC0415
        from datacloud_analysis.tools.skill import build_skill  # noqa: PLC0415
        from datacloud_analysis.memory.tools import recall_memory  # noqa: PLC0415

        _TASK_DISPATCHERS.update(
            {
                "data_query": data_query,
                "code_exec": sbx_run_code,
                "file_read": sbx_read_file,
                "file_write": sbx_write_file,
                "search_knowledge": search_knowledge,
                "recall_memory": recall_memory,
                "build_skill": build_skill,
                "render_report": render_report,
            }
        )
    except ImportError as exc:
        logger.warning("Could not register all dispatchers: %s", exc)
