"""Sandbox task dispatcher (design §3.1 DO_TASK / TOOLBOX).

This module maps a sub-task type to the corresponding tool function and
runs it inside the current sandbox context.

Sub-task types → tools
----------------------
dynamic query   → injected by worker/custom_tools
code_exec       → tools.sandbox.sbx_run_code
file_read       → tools.sandbox.sbx_read_file
file_write      → tools.sandbox.sbx_write_file
search_knowledge→ tools.knowledge.search_knowledge
recall_memory   → memory.tools.recall_memory
build_skill     → tools.skill.build_skill
render_report   → tools.report.render_report
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Registry: task type → callable (populated lazily to avoid circular imports)
_TASK_DISPATCHERS: dict[str, Any] = {}


async def execute_next_task(
    task: dict[str, Any],
    state: dict[str, Any],
    custom_tools: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any]:
    """Execute one sub-task and return the updated task dict and output.

    Args:
        task:  Sub-task dict from the DAG (must have ``id`` and ``type``).
        state: Current graph state (for context / message history).

    Returns:
        (updated_task, output)
    """
    task_type: str = task.get("type", "unknown")
    dispatcher = _get_dispatcher(task_type)
    dynamic_dispatcher = (custom_tools or {}).get(task_type)

    if dispatcher is None and dynamic_dispatcher is None:
        logger.warning("No dispatcher for task type '%s'; marking as failed.", task_type)
        output = f"Unknown task type: {task_type}"
        return {**task, "status": "failed", "error": output}, output

    try:
        logger.debug("Executing task %s (type=%s) …", task["id"], task_type)
        
        # Tools are BaseTool instances, so we call ainvoke.
        # But wait, some might be functions. Let's handle tool properly.
        if dynamic_dispatcher is not None:
            planned_params = task.get("params", {})
            params = (
                planned_params.copy()
                if isinstance(planned_params, dict)
                else {}
            )
            if (
                "question" not in params
                and "query" not in params
                and task.get("description")
            ):
                params["question"] = str(task.get("description"))
            is_consistent = params == planned_params
            logger.info(
                "Task %s planned params: %s",
                task["id"],
                planned_params,
            )
            logger.info(
                "Task %s execution params: %s",
                task["id"],
                params,
            )
            logger.info(
                "Task %s params consistent: %s",
                task["id"],
                is_consistent,
            )
            if hasattr(dynamic_dispatcher, "ainvoke"):
                output = await dynamic_dispatcher.ainvoke(params)
            elif callable(dynamic_dispatcher):
                maybe = dynamic_dispatcher(**params) if isinstance(params, dict) else dynamic_dispatcher(params)
                output = await maybe if hasattr(maybe, "__await__") else maybe
            else:
                output = dynamic_dispatcher
        elif hasattr(dispatcher, "ainvoke"):
            # Prepare params. Usually the LLM outputs 'description' which we might map to 'query' or 'question'.
            params = {}
            if task_type == "code_exec":
                params = task.get("params", {}).copy()
                dep_ids = task.get("deps", [])
                if dep_ids:
                    params["input_files"] = _resolve_input_files(dep_ids, state)
            else:
                params = task.get("params", {})
            output = await dispatcher.ainvoke(params)
        else:
            output = await dispatcher(task.get("params", {}), state)

        # code_exec: treat non-zero exit_code as task failure
        if task_type == "code_exec" and isinstance(output, dict) and output.get("exit_code", 0) != 0:
            error_msg = output.get("output", "代码执行失败（未知错误）")
            logger.warning("Task %s (code_exec) failed: %s", task["id"], error_msg[:200])
            return {**task, "status": "failed", "error": error_msg}, output

        return {**task, "status": "done"}, output
    except Exception as exc:  # noqa: BLE001
        logger.error("Task %s failed: %s", task["id"], exc)
        return {**task, "status": "failed", "error": str(exc)}, str(exc)


def _get_dispatcher(task_type: str) -> Any | None:
    """Return the async callable for the given task type (lazy import)."""
    if not _TASK_DISPATCHERS:
        _register_dispatchers()
    return _TASK_DISPATCHERS.get(task_type)


def _register_dispatchers() -> None:
    """Populate the dispatcher registry (called once on first use)."""
    try:
        from datacloud_analysis.tools.knowledge import search_knowledge  # noqa: PLC0415
        from datacloud_analysis.tools.report import render_report  # noqa: PLC0415
        from datacloud_analysis.tools.sandbox import sbx_read_file, sbx_run_code, sbx_write_file  # noqa: PLC0415
        from datacloud_analysis.tools.skill import build_skill  # noqa: PLC0415
        from datacloud_analysis.memory.tools import recall_memory  # noqa: PLC0415

        _TASK_DISPATCHERS.update(
            {
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


def _resolve_input_files(dep_ids: list[str], state: dict[str, Any]) -> dict[str, str]:
    """Build a mapping of dep task_id → JSONL file path for code_exec tasks.

    For each dep task, reads the intermediate temp JSON (written by loop_node),
    then extracts the actual JSONL file path stored inside the query output.
    Falls back to the temp JSON path itself if no inner file_path is found.

    Args:
        dep_ids: List of dependency task IDs (e.g. ["t1", "t2"]).
        state:   Current graph state containing the "results" list.

    Returns:
        dict mapping task_id → absolute file path readable by the code.
    """
    dep_set = set(dep_ids)
    input_files: dict[str, str] = {}

    for res in state.get("results", []):
        task_id = res.get("task_id")
        if task_id not in dep_set:
            continue

        # Multi-task path: loop_node saved output to temp/{task_id}.json
        temp_path = res.get("file_path")
        if temp_path and Path(temp_path).exists():
            try:
                with open(temp_path, encoding="utf-8") as f:
                    task_output = json.load(f)
                # query output contains a nested "file_path" pointing to the JSONL
                jsonl_path = task_output.get("file_path")
                if jsonl_path and Path(jsonl_path).exists():
                    input_files[task_id] = jsonl_path
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("_resolve_input_files: failed to read %s: %s", temp_path, exc)
            # Fallback: use the temp JSON itself
            input_files[task_id] = temp_path
            continue

        # Single-task path: output kept in memory under "data" key
        data = res.get("data")
        if isinstance(data, dict):
            jsonl_path = data.get("file_path")
            if jsonl_path and Path(jsonl_path).exists():
                input_files[task_id] = jsonl_path

    missing = dep_set - set(input_files)
    if missing:
        logger.warning("_resolve_input_files: could not resolve file paths for deps: %s", missing)

    return input_files
