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


async def loop_node(
    state: AgentState,
    default_tools: dict | None = None,
) -> dict:
    """One round of the ReAct loop.

    Executes ALL currently-ready tasks (deps satisfied) concurrently,
    then returns updated plan + results so the router can decide whether
    to loop again or proceed to insight.
    """
    plan = state.get("plan", [])
    results = list(state.get("results", []))  # copy — LangGraph merges via reducer
    workspace_dir = state.get("workspace_dir")
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}

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

    updated_plan = list(plan)
    context = state.get("gateway_context")

    # ── 执行前：逐任务推送"开始执行"日志（含工具名和入参）──────────────
    if context is not None:
        for t in ready_tasks:
            params_text = _format_params(t.get("params", {}))
            pre_thinking = (
                f"▶ 开始执行 [{t['id']}]：{t.get('description', '')}\n"
                f"■ 工具：{t.get('type', '未知')}\n"
                f"■ 入参：{params_text}"
            )
            await context.emit_chunk(
                StreamChunkEvent(content="执行任务"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_title.value,
            )
            await context.emit_chunk(
                StreamChunkEvent(content=pre_thinking),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_text.value,
            )

    # ── Concurrent execution ────────────────────────────────────────────
    task_outputs: list[tuple[dict, Any]] = await asyncio.gather(
        *[execute_next_task(t, state, custom_tools=dynamic_tools) for t in ready_tasks]
    )

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

        # ── 执行后：推送"完成/失败"日志（含工具名、入参、出参）──────────
        if context is not None:
            total = len(updated_plan)
            done_count = sum(
                1 for t in updated_plan if t.get("status") in ("done", "failed")
            )
            status_icon = "✓" if updated_task.get("status") == "done" else "✗"
            params_text = _format_params(updated_task.get("params", {}))
            output_text = _format_output(output)
            thinking = (
                f"[{status_icon} {done_count}/{total}] [{updated_task['id']}]："
                f"{updated_task.get('description', '')}\n"
                f"■ 工具：{updated_task.get('type', '未知')}\n"
                f"■ 入参：{params_text}\n"
                f"■ 出参：{output_text}"
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


def _format_params(params: Any, max_len: int = 500) -> str:
    """将工具入参格式化为可读字符串，超长时截断。"""
    if not params:
        return "（无）"
    try:
        text = json.dumps(params, ensure_ascii=False, indent=None)
    except Exception:
        text = str(params)
    if len(text) > max_len:
        text = text[:max_len] + "…（已截断）"
    return text


def _format_output(output: Any, max_len: int = 500) -> str:
    """将工具出参格式化为可读摘要，区分常见结构类型。"""
    if output is None:
        return "（无结果）"
    if isinstance(output, dict):
        # records + meta 格式（在线查数标准返回）
        if "records" in output and "meta" in output:
            records = output.get("records", [])
            meta = output.get("meta", {}) if isinstance(output.get("meta"), dict) else {}
            total = meta.get("total", len(records))
            cols = [c.get("name", "") if isinstance(c, dict) else str(c)
                    for c in (meta.get("columns") or [])]
            cols_str = ", ".join(cols[:8]) + ("…" if len(cols) > 8 else "")
            return (
                f"records: {len(records)} 条（total={total}）"
                + (f"，columns: [{cols_str}]" if cols_str else "")
            )
        # preview + columns 格式
        if "preview" in output and "columns" in output:
            preview = output.get("preview", [])
            total = output.get("total", len(preview))
            cols = [c.get("name", "") if isinstance(c, dict) else str(c)
                    for c in (output.get("columns") or [])]
            cols_str = ", ".join(cols[:8]) + ("…" if len(cols) > 8 else "")
            return (
                f"preview: {len(preview)} 条（total={total}）"
                + (f"，columns: [{cols_str}]" if cols_str else "")
            )
        # code_exec 格式
        if "exit_code" in output:
            exit_code = output.get("exit_code", 0)
            stdout = str(output.get("output", "")).strip()[:200]
            result = output.get("result")
            result_info = (
                f"，result: {len(result)} 行" if isinstance(result, list) else ""
            )
            status_str = "成功" if exit_code == 0 else f"失败(exit_code={exit_code})"
            return f"{status_str}{result_info}" + (f"，stdout: {stdout!r}" if stdout else "")
        # 通用 dict
        try:
            text = json.dumps(output, ensure_ascii=False)
        except Exception:
            text = str(output)
        if len(text) > max_len:
            text = text[:max_len] + "…（已截断）"
        return text
    if isinstance(output, str):
        text = output.strip()
        if len(text) > max_len:
            text = text[:max_len] + "…（已截断）"
        return text if text else "（空字符串）"
    try:
        text = json.dumps(output, ensure_ascii=False)
    except Exception:
        text = repr(output)
    if len(text) > max_len:
        text = text[:max_len] + "…（已截断）"
    return text
