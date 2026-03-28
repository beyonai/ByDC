"""Sandbox task dispatcher (design §3.1 DO_TASK / TOOLBOX).

This module maps a sub-task type to the corresponding tool function and
runs it inside the current sandbox context.

Sub-task types → tools
----------------------
dynamic query   → injected by worker/custom_tools
code_exec       → tools.sandbox.sbx_run_code
file_read       → tools.sandbox.sbx_read_file
file_write      → tools.sandbox.sbx_write_file
recall_memory   → memory.tools.recall_memory
build_skill     → tools.skill.build_skill
render_report   → tools.report.render_report
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from datacloud_analysis.orchestration.query_shape_utils import count_rows_like_envelope_build

logger = logging.getLogger(__name__)

# Workspace temp JSON must be a JSON object/array so downstream can json.load → dict/list.
# Tools that return plain str would otherwise serialize as a JSON string
# and break _resolve_input_files / insight readers that call .get on the payload.
WRAPPED_TASK_OUTPUT_KEY = "_datacloud_wrapped_output"


def normalize_workspace_task_output(output: Any) -> Any:
    """Return a value safe to json.dump into workspace temp/{task_id}.json.

    Dict/list outputs are stored as-is; scalars (e.g. str) are wrapped in a small object.
    """
    if isinstance(output, (dict, list)):
        return output
    return {WRAPPED_TASK_OUTPUT_KEY: True, "kind": "text", "content": output}

# Registry: task type → callable (populated lazily to avoid circular imports)
_TASK_DISPATCHERS: dict[str, Any] = {}


class _NullContext:
    """当 datacloud_data_sdk 不可用时的空上下文管理器兜底。"""

    def __enter__(self) -> "_NullContext":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


def _log_tool_output_summary(task_id: str, task_type: str, output: Any) -> None:
    """Log a compact summary of tool return (counts/ids only, not full rows or polygon)."""
    if isinstance(output, dict):
        recs = output.get("records")
        n_records = len(recs) if isinstance(recs, list) else None
        prev = output.get("preview")
        n_preview = len(prev) if isinstance(prev, list) else None
        shaped_rows = count_rows_like_envelope_build(output)
        meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
        meta_total = meta.get("total")
        object_id = str(meta.get("objectId", "") or "")
        has_plan = "plan" in output
        logger.info(
            "[tool return] task_id=%s type=%s records=%s preview=%s shaped_rows=%s "
            "meta.total=%s objectId=%s has_plan=%s",
            task_id,
            task_type,
            n_records,
            n_preview,
            shaped_rows,
            meta_total,
            object_id,
            has_plan,
        )
        return
    if isinstance(output, str):
        logger.info(
            "[tool return] task_id=%s type=%s output=str len=%d preview=%s",
            task_id,
            task_type,
            len(output),
            output[:240].replace("\n", " "),
        )
        return
    logger.info(
        "[tool return] task_id=%s type=%s output_type=%s repr_preview=%s",
        task_id,
        task_type,
        type(output).__name__,
        repr(output)[:240],
    )


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
        if not _TASK_DISPATCHERS:
            _register_dispatchers()
        builtin_keys = sorted(_TASK_DISPATCHERS.keys())
        custom_keys = sorted((custom_tools or {}).keys())
        logger.warning(
            "No dispatcher for task type %r (task_id=%s); marking as failed. "
            "Compare: model/plan used this string as 'type'. "
            "dynamic_tools keys at execution (count=%d)=%s. "
            "sandbox built-in types (count=%d)=%s.",
            task_type,
            task.get("id"),
            len(custom_keys),
            custom_keys,
            len(builtin_keys),
            builtin_keys,
        )
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
            # 建立 InvocationContext，将 gateway_context 传入 SDK 层，
            # 使 get_current_context() 和 get_gateway_context() 在 SDK 内部可用
            try:
                from datacloud_data_sdk.context import InvocationContext  # noqa: PLC0415
                gateway_context = state.get("gateway_context")
                _ctx_kwargs: dict = {}
                if gateway_context is not None:
                    _ctx_kwargs["gateway_context"] = gateway_context
                    _ctx_kwargs["session_id"] = getattr(gateway_context, "session_id", "")
                _invocation_ctx: Any = InvocationContext(**_ctx_kwargs)
            except ImportError:
                _invocation_ctx = _NullContext()

            with _invocation_ctx:
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

        _log_tool_output_summary(str(task.get("id", "?")), task_type, output)
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
        from datacloud_analysis.tools.report import render_report  # noqa: PLC0415
        from datacloud_analysis.tools.sandbox import sbx_read_file, sbx_run_code, sbx_write_file  # noqa: PLC0415
        from datacloud_analysis.tools.skill import build_skill  # noqa: PLC0415
        from datacloud_analysis.memory.tools import recall_memory  # noqa: PLC0415

        _TASK_DISPATCHERS.update(
            {
                "code_exec": sbx_run_code,
                "file_read": sbx_read_file,
                "file_write": sbx_write_file,
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("_resolve_input_files: failed to read %s: %s", temp_path, exc)
                input_files[task_id] = temp_path
                continue

            if isinstance(task_output, dict):
                if task_output.get(WRAPPED_TASK_OUTPUT_KEY):
                    text = str(task_output.get("content", ""))
                    dep_txt = Path(temp_path).with_name(f"{task_id}_dep_input.txt")
                    try:
                        dep_txt.write_text(text, encoding="utf-8")
                        input_files[task_id] = str(dep_txt.resolve())
                    except OSError as wexc:
                        logger.warning(
                            "_resolve_input_files: could not write %s: %s", dep_txt, wexc
                        )
                    continue
                jsonl_path = task_output.get("file_path")
                if jsonl_path and Path(jsonl_path).exists():
                    input_files[task_id] = jsonl_path
                    continue
            elif isinstance(task_output, str):
                # Legacy files: json.dump(str) produced a JSON string document
                dep_txt = Path(temp_path).with_name(f"{task_id}_dep_input.txt")
                try:
                    dep_txt.write_text(task_output, encoding="utf-8")
                    input_files[task_id] = str(dep_txt.resolve())
                except OSError as wexc:
                    logger.warning(
                        "_resolve_input_files: could not write %s: %s", dep_txt, wexc
                    )
                continue

            # Fallback: temp JSON path (structured dict without file_path, etc.)
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
