"""Sandbox task dispatcher (design 搂3.1 DO_TASK / TOOLBOX).

This module maps a sub-task type to the corresponding tool function and
runs it inside the current sandbox context.

Sub-task types 鈫?tools
----------------------
dynamic query   鈫?injected by worker/custom_tools
code_exec       鈫?tools.sandbox.sbx_run_code
file_read       鈫?tools.sandbox.sbx_read_file
file_write      鈫?tools.sandbox.sbx_write_file
recall_memory   鈫?memory.tools.recall_memory
build_skill     鈫?tools.skill.build_skill
render_report   鈫?tools.report.render_report
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from langgraph.types import interrupt

from datacloud_analysis.orchestration.query_shape_utils import count_rows_like_envelope_build
from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext, HookDecision, HookError

try:
    from langgraph.errors import GraphInterrupt
except ImportError:  # pragma: no cover
    GraphInterrupt = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Workspace temp JSON must be a JSON object/array so downstream can json.load 鈫?dict/list.
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

# Registry: task type 鈫?callable (populated lazily to avoid circular imports)
_TASK_DISPATCHERS: dict[str, Any] = {}


class _NullContext:
    """Fallback no-op context manager when datacloud_data_sdk is unavailable."""

    def __enter__(self) -> _NullContext:
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
        raw_meta = output.get("meta")
        meta = raw_meta if isinstance(raw_meta, dict) else {}
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


def _build_hook_context(
    *,
    task: dict[str, Any],
    state: Mapping[str, Any],
    gateway_context: Any,
    params: dict[str, Any],
) -> HookContext:
    session_id = ""
    if gateway_context is not None:
        session_id = str(getattr(gateway_context, "session_id", "") or "")
    query_text = ""
    messages = state.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        query_text = str(getattr(last, "content", "") or "")
    resume_context = state.get("resume_context")
    resume_map = resume_context if isinstance(resume_context, dict) else {}
    return {
        "session_id": session_id,
        "thread_id": session_id,
        "agent_id": str(state.get("agent_id") or "") or None,
        "checkpoint_id": str(resume_map.get("checkpoint_id") or "") or None,
        "checkpoint_ns": str(resume_map.get("checkpoint_ns") or "") or None,
        "todo_id": str(task.get("id") or ""),
        "react_step_id": str(task.get("id") or ""),
        "tool_name": str(task.get("type") or ""),
        "tool_params": dict(params),
        "user_query": query_text,
        "enriched_query": (
            str(state.get("enriched_query") or "")
            or (str(state.get("intent") or "") if state.get("intent") else None)
        ),
        "term_context": list(_todo_term_context(state, task)),
        "knowledge_snippets": list(state.get("knowledge_snippets") or []),
        "workspace_dir": str(state.get("workspace_dir") or "") or None,
        "tool_output": None,
        "tool_error": None,
        "metadata": {
            "task_description": str(task.get("description") or ""),
            "todo_goal": str(_todo_goal(state, task) or ""),
        },
    }


def _todo_term_context(state: Mapping[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = str(task.get("id") or "")
    for todo in (state.get("todos") or []):
        if not isinstance(todo, dict):
            continue
        if str(todo.get("todo_id") or "") == task_id:
            value = todo.get("term_context")
            return value if isinstance(value, list) else []
    confirmed_terms = state.get("confirmed_terms")
    return confirmed_terms if isinstance(confirmed_terms, list) else []


def _todo_goal(state: Mapping[str, Any], task: dict[str, Any]) -> str:
    task_id = str(task.get("id") or "")
    for todo in (state.get("todos") or []):
        if not isinstance(todo, dict):
            continue
        if str(todo.get("todo_id") or "") == task_id:
            return str(todo.get("goal") or "")
    return ""


def _decision_action(decision: HookDecision | None) -> str:
    if not isinstance(decision, dict):
        return "continue"
    action = str(decision.get("action") or "").strip().lower()
    if action:
        return action
    # Backward-compatible decision schema.
    if bool(decision.get("short_circuit")):
        return "short_circuit"
    if bool(decision.get("block")):
        return "fail"
    if bool(decision.get("recover")):
        return "recover"
    if bool(decision.get("raise")):
        return "fail"
    return "continue"


def _decision_output(decision: HookDecision | None) -> Any:
    if not isinstance(decision, dict):
        return None
    if "output" in decision:
        return decision.get("output")
    result = decision.get("result")
    if not isinstance(result, dict):
        return None
    return result.get("tool_output")


def _decision_error_text(decision: HookDecision | None, default: str) -> str:
    if not isinstance(decision, dict):
        return default
    if isinstance(decision.get("error"), str) and str(decision.get("error")).strip():
        return str(decision.get("error")).strip()
    result = decision.get("result")
    if not isinstance(result, dict):
        return default
    err = result.get("tool_error")
    if isinstance(err, dict):
        message = str(err.get("message") or "").strip()
        if message:
            return message
    return default


def _prepare_dynamic_callable_kwargs(
    *,
    dynamic_dispatcher: Any,
    params: dict[str, Any],
    task_description: str,
    gateway_context: Any,
) -> dict[str, Any]:
    """Adapt kwargs for plain-callable dynamic tools using signature hints."""
    call_kwargs = dict(params)
    if not callable(dynamic_dispatcher):
        return call_kwargs

    try:
        signature = inspect.signature(dynamic_dispatcher)
    except (TypeError, ValueError):
        return call_kwargs

    parameters = signature.parameters
    accepts_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()
    )

    if "content" in parameters and "content" not in call_kwargs:
        raw_content = (
            call_kwargs.get("question")
            or call_kwargs.get("query")
            or call_kwargs.get("description")
            or task_description
        )
        call_kwargs["content"] = str(raw_content or "")

    if "_context" in parameters and "_context" not in call_kwargs and gateway_context is not None:
        call_kwargs["_context"] = gateway_context

    if accepts_var_kwargs:
        return call_kwargs
    return {key: value for key, value in call_kwargs.items() if key in parameters}


def _ensure_dynamic_content_param(params: dict[str, Any], task_description: str) -> dict[str, Any]:
    """Ensure dynamic dispatch payload contains ``content`` when possible."""
    if str(params.get("content", "")).strip():
        return params
    raw_content = (
        params.get("question")
        or params.get("query")
        or params.get("description")
        or task_description
    )
    if raw_content not in (None, ""):
        params["content"] = str(raw_content)
    return params


async def execute_next_task(
    task: dict[str, Any],
    state: Mapping[str, Any],
    gateway_context: Any = None,
    custom_tools: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any]:
    """Execute one sub-task and return the updated task dict and output.

    Args:
        task:  Sub-task dict from the DAG (must have `id` and `type`).
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
        unknown_output = f"Unknown task type: {task_type}"
        return {**task, "status": "failed", "error": unknown_output}, unknown_output

    params: dict[str, Any]
    if dynamic_dispatcher is not None:
        planned_params = task.get("params", {})
        params = planned_params.copy() if isinstance(planned_params, dict) else {}
        if "question" not in params and "query" not in params and task.get("description"):
            params["question"] = str(task.get("description"))
        params = _ensure_dynamic_content_param(params, str(task.get("description") or ""))
        logger.info("Task %s planned params: %s", task["id"], planned_params)
        logger.info("Task %s execution params: %s", task["id"], params)
        logger.info("Task %s params consistent: %s", task["id"], params == planned_params)
    elif task_type == "code_exec":
        raw_params = task.get("params", {})
        params = raw_params.copy() if isinstance(raw_params, dict) else {}
        dep_ids = task.get("deps", [])
        if dep_ids:
            params["input_files"] = _resolve_input_files(dep_ids, state)
    else:
        raw_params = task.get("params", {})
        params = raw_params if isinstance(raw_params, dict) else {}

    hook_manager = get_tool_hook_plugin_manager()
    hook_context = _build_hook_context(
        task=task,
        state=state,
        gateway_context=gateway_context,
        params=params,
    )
    hook_context, before_decision = await hook_manager.run_before(hook_context)
    params = dict(hook_context.get("tool_params") or params)
    _log_hook_decision("before", before_decision, task_id=str(task.get("id") or "?"))

    before_action = _decision_action(before_decision)
    if before_action == "short_circuit":
        short_circuit_output = _decision_output(before_decision)
        _log_tool_output_summary(str(task.get("id", "?")), task_type, short_circuit_output)
        return {**task, "status": "done"}, short_circuit_output
    if before_action == "fail":
        error_text = _decision_error_text(before_decision, "Tool blocked by hook plugin")
        return {**task, "status": "failed", "error": error_text}, error_text
    if before_action == "interrupt":
        interrupt_payload = {}
        if isinstance(before_decision, dict) and isinstance(before_decision.get("interrupt"), dict):
            interrupt_payload = dict(before_decision["interrupt"])
        interrupt_payload.setdefault("todo_id", str(task.get("id") or ""))
        interrupt_payload.setdefault("react_step_id", str(task.get("id") or ""))
        interrupt_payload.setdefault("tool_name", str(task.get("type") or ""))
        resume_value = interrupt(interrupt_payload)
        if isinstance(resume_value, dict):
            params.update(resume_value)
        elif resume_value not in (None, ""):
            params["resume_input"] = resume_value

    output: Any = None
    try:
        logger.debug("Executing task %s (type=%s)", task.get("id"), task_type)
        if dynamic_dispatcher is not None:
            try:
                from datacloud_data_sdk.context import InvocationContext  # noqa: PLC0415

                ctx_kwargs: dict[str, Any] = {}
                if gateway_context is not None:
                    ctx_kwargs["gateway_context"] = gateway_context
                    ctx_kwargs["session_id"] = getattr(gateway_context, "session_id", "")
                invocation_ctx: Any = InvocationContext(**ctx_kwargs)
            except ImportError:
                invocation_ctx = _NullContext()

            with invocation_ctx:
                if hasattr(dynamic_dispatcher, "ainvoke"):
                    try:
                        output = await dynamic_dispatcher.ainvoke(params)
                    except TypeError as exc:
                        # Some wrappers expose ``ainvoke`` but still require function-style kwargs.
                        err_text = str(exc)
                        if "required positional argument: 'content'" not in err_text or not callable(
                            dynamic_dispatcher
                        ):
                            raise
                        call_kwargs = _prepare_dynamic_callable_kwargs(
                            dynamic_dispatcher=dynamic_dispatcher,
                            params=params,
                            task_description=str(task.get("description") or ""),
                            gateway_context=gateway_context,
                        )
                        maybe = dynamic_dispatcher(**call_kwargs)
                        output = await maybe if hasattr(maybe, "__await__") else maybe
                elif callable(dynamic_dispatcher):
                    call_kwargs = _prepare_dynamic_callable_kwargs(
                        dynamic_dispatcher=dynamic_dispatcher,
                        params=params,
                        task_description=str(task.get("description") or ""),
                        gateway_context=gateway_context,
                    )
                    maybe = dynamic_dispatcher(**call_kwargs)
                    output = await maybe if hasattr(maybe, "__await__") else maybe
                else:
                    output = dynamic_dispatcher
        else:
            if dispatcher is None:
                raise RuntimeError(f"No dispatcher for task type: {task_type}")
            if hasattr(dispatcher, "ainvoke"):
                output = await dispatcher.ainvoke(params)
            else:
                output = await dispatcher(params, state)

        after_context = cast(HookContext, dict(hook_context))
        after_context["tool_params"] = dict(params)
        after_context["tool_output"] = output
        after_context["tool_error"] = None
        after_context, after_decision = await hook_manager.run_after(after_context)
        _log_hook_decision("after", after_decision, task_id=str(task.get("id") or "?"))
        after_action = _decision_action(after_decision)
        if after_action == "recover":
            output = _decision_output(after_decision)
        elif after_action == "fail":
            error_text = _decision_error_text(after_decision, "Tool failed after hook processing")
            return {**task, "status": "failed", "error": error_text}, error_text
        elif after_context.get("tool_output") is not None:
            output = cast(Any, after_context.get("tool_output"))

        if task_type == "code_exec" and isinstance(output, dict) and output.get("exit_code", 0) != 0:
            error_msg = str(output.get("output", "代码执行失败（未知错误）"))
            logger.warning("Task %s (code_exec) failed: %s", task["id"], error_msg[:200])
            return {**task, "status": "failed", "error": error_msg}, output

        _log_tool_output_summary(str(task.get("id", "?")), task_type, output)
        return {**task, "status": "done"}, output
    except GraphInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        error_data: HookError = {"error_type": type(exc).__name__, "message": str(exc)}
        after_context = cast(HookContext, dict(hook_context))
        after_context["tool_params"] = dict(params)
        after_context["tool_output"] = None
        after_context["tool_error"] = error_data
        after_context, after_decision = await hook_manager.run_after(after_context)
        _log_hook_decision("after", after_decision, task_id=str(task.get("id") or "?"))
        after_action = _decision_action(after_decision)
        if after_action == "recover":
            recovered_output = _decision_output(after_decision)
            _log_tool_output_summary(str(task.get("id", "?")), task_type, recovered_output)
            return {**task, "status": "done"}, recovered_output
        if after_action == "fail":
            error_text = _decision_error_text(after_decision, str(exc))
            logger.error("Task %s failed after hook decision: %s", task["id"], error_text)
            return {**task, "status": "failed", "error": error_text}, error_text
        logger.error("Task %s failed: %s", task["id"], exc)
        return {**task, "status": "failed", "error": str(exc)}, str(exc)


def _log_hook_decision(phase: str, decision: HookDecision | None, *, task_id: str) -> None:
    if not isinstance(decision, dict):
        return
    audit = decision.get("audit")
    if not isinstance(audit, dict):
        return
    plugin_id = str(audit.get("plugin_id") or "").strip() or "unknown"
    message = str(audit.get("message") or "").strip() or "-"
    risk = str(audit.get("risk_level") or "unknown")
    action = _decision_action(decision)
    logger.info(
        "tool_hook_%s: task_id=%s plugin_id=%s action=%s risk=%s message=%s",
        phase,
        task_id,
        plugin_id,
        action,
        risk,
        message,
    )

def _get_dispatcher(task_type: str) -> Any | None:
    """Return the async callable for the given task type (lazy import)."""
    if not _TASK_DISPATCHERS:
        _register_dispatchers()
    return _TASK_DISPATCHERS.get(task_type)


def _register_dispatchers() -> None:
    """Populate the dispatcher registry (called once on first use)."""
    try:
        from datacloud_analysis.memory.tools import recall_memory  # noqa: PLC0415
        from datacloud_analysis.tools.report import render_report  # noqa: PLC0415
        from datacloud_analysis.tools.sandbox import (  # noqa: PLC0415
            sbx_read_file,
            sbx_run_code,
            sbx_write_file,
        )
        from datacloud_analysis.tools.skill import build_skill  # noqa: PLC0415

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


def _resolve_input_files(dep_ids: list[str], state: Mapping[str, Any]) -> dict[str, str]:
    """Build a mapping of dep task_id 鈫?JSONL file path for code_exec tasks.

    For each dep task, reads the intermediate temp JSON (written by loop_node),
    then extracts the actual JSONL file path stored inside the query output.
    Falls back to the temp JSON path itself if no inner file_path is found.

    Args:
        dep_ids: List of dependency task IDs (e.g. ["t1", "t2"]).
        state:   Current graph state containing the "results" list.

    Returns:
        dict mapping task_id 鈫?absolute file path readable by the code.
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



