"""④ Summary and reply generation (design §3.1 INSIGHT).

Responsibilities
----------------
- Collect outputs from all completed sub-tasks (from state results or workspace).
- Format structured query results as Markdown tables; format code_exec results from _result.
- Emit results in THREE separate ANSWER_DELTA messages:
    Part1 — Analysis report  (LLM-generated text, streamed token by token)
    Part2 — Data tables      (Markdown tables, emitted as one block)
    Part3 — File information (file paths + download URLs, emitted as one block)
- For single structured-result tasks, skip LLM and emit Part2/Part3 directly.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseMessageType, SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result formatters  (unchanged from previous version)
# ---------------------------------------------------------------------------

def _format_data_query_result(task_id: str, output: dict) -> str:
    """Convert a structured query output dict into a Markdown table string."""
    preview = output.get("preview", [])
    total = output.get("total", len(preview))
    columns = output.get("columns", [])
    file_path = output.get("file_path", "")
    overflow_notice = output.get("overflow_notice", "")

    md_lines: list[str] = []
    if columns:
        headers = [col.get("label", col.get("name", "")) for col in columns]
        keys = [col.get("name") for col in columns]
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in preview:
            cells = [str(row.get(k, "")) for k in keys]
            md_lines.append("| " + " | ".join(cells) + " |")

    md_table = "\n".join(md_lines)

    if not overflow_notice:
        if total > len(preview):
            overflow_notice = (
                f"*【重要】数据量较大（共 {total} 条），"
                f"此处仅展示前 {len(preview)} 条。详细数据路径: {file_path}*"
            )
        else:
            overflow_notice = f"*共 {total} 条，已全量展示。*"

    return f"【数据查询结果】\n{md_table}\n{overflow_notice}"


def _format_records_meta_result(task_id: str, output: dict) -> str:
    """Format query output shaped as {records, meta} into Markdown."""
    records = output.get("records", [])
    meta = output.get("meta", {}) if isinstance(output.get("meta"), dict) else {}
    total = int(meta.get("total", len(records))) if isinstance(meta, dict) else len(records)

    columns_meta = meta.get("columns", []) if isinstance(meta, dict) else []
    keys: list[str] = []
    if columns_meta and isinstance(columns_meta, list):
        for col in columns_meta:
            if isinstance(col, dict):
                name = str(col.get("name", "")).strip()
                if name:
                    keys.append(name)
            elif isinstance(col, str):
                keys.append(col)

    if not keys and isinstance(records, list) and records and isinstance(records[0], dict):
        keys = list(records[0].keys())

    preview = records if isinstance(records, list) else []
    preview_count = min(len(preview), 10)
    preview_rows = preview[:preview_count]

    md_lines: list[str] = []
    if keys:
        md_lines.append("| " + " | ".join(keys) + " |")
        md_lines.append("|" + "|".join(["---"] * len(keys)) + "|")
        for row in preview_rows:
            cells = [str(row.get(k, "")) if isinstance(row, dict) else "" for k in keys]
            md_lines.append("| " + " | ".join(cells) + " |")

    md_table = "\n".join(md_lines)
    if total > preview_count:
        notice = f"*【重要】数据量较大（共 {total} 条），此处仅展示前 {preview_count} 条。*"
    else:
        notice = f"*共 {total} 条，已全量展示。*"
    return f"【数据查询结果】\n{md_table}\n{notice}"


def _format_code_exec_result(output: dict) -> str:
    """Convert a code_exec tool output dict into a Markdown string."""
    exit_code = output.get("exit_code", 0)
    stdout_output = output.get("output", "")
    result_payload = output.get("result")

    if exit_code != 0:
        return f"【代码执行失败】\n```\n{stdout_output}\n```"

    if (
        isinstance(result_payload, list)
        and result_payload
        and isinstance(result_payload[0], dict)
    ):
        headers = list(result_payload[0].keys())
        md_lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
        for row in result_payload:
            cells = [str(row.get(h, "")) for h in headers]
            md_lines.append("| " + " | ".join(cells) + " |")
        md_table = "\n".join(md_lines)
        formatted = f"【计算结果】\n{md_table}"
        if stdout_output.strip():
            formatted += f"\n\n输出摘要：\n```\n{stdout_output.strip()[:500]}\n```"
        return formatted

    if result_payload is not None:
        formatted = f"【计算结果】\n{result_payload}"
        if stdout_output.strip():
            formatted += f"\n\n输出摘要：\n```\n{stdout_output.strip()[:500]}\n```"
        return formatted

    return f"【代码执行输出】\n```\n{stdout_output}\n```"


def _aggregate_result(res: dict) -> dict[str, Any] | None:
    """Normalise one entry from state['results'] into {task_id, data}.

    Handles three layouts produced by loop_node:
      1. {"task_id": ..., "data": <query or code_exec output dict>}
         — single-task in-memory path
      2. {"task_id": ..., "file_path": "/workspace/temp/t1.json"}
         — multi-task workspace path (JSON contains the tool output)
      3. Anything else — passed through as-is
    """
    task_id = res.get("task_id", "?")

    if "data" in res:
        output = res["data"]
        if isinstance(output, dict):
            if "records" in output and "meta" in output:
                return {"task_id": task_id, "data": _format_records_meta_result(task_id, output)}
            if "preview" in output and "columns" in output:
                return {"task_id": task_id, "data": _format_data_query_result(task_id, output)}
            if "exit_code" in output:
                return {"task_id": task_id, "data": _format_code_exec_result(output)}
        return res

    if "file_path" in res:
        try:
            with open(res["file_path"], "r", encoding="utf-8") as f:
                output = json.load(f)
            if isinstance(output, dict):
                if "records" in output and "meta" in output:
                    return {"task_id": task_id, "data": _format_records_meta_result(task_id, output)}
                if "preview" in output and "columns" in output:
                    return {"task_id": task_id, "data": _format_data_query_result(task_id, output)}
                if "exit_code" in output:
                    return {"task_id": task_id, "data": _format_code_exec_result(output)}
            return {"task_id": task_id, "data": output}
        except Exception as exc:
            logger.error("Failed to read intermediate result %s: %s", res["file_path"], exc)
            return None

    return res


# ---------------------------------------------------------------------------
# Three-part content extractors
# ---------------------------------------------------------------------------

def _extract_tables_md(aggregated_data: list[dict]) -> str:
    """Extract all Markdown tables from aggregated_data and combine into one block.

    Returns an empty string if no tables are present.
    """
    table_blocks: list[str] = []
    for item in aggregated_data:
        data = item.get("data", "")
        if isinstance(data, str) and (
            "【数据查询结果】" in data or "【计算结果】" in data
        ):
            table_blocks.append(data)
    return "\n\n---\n\n".join(table_blocks)


def _extract_file_info_md(results: list[dict]) -> str:
    """Extract file_path and download_url from raw results and format as Markdown.

    Returns an empty string if no file info is available.
    """
    lines: list[str] = []
    for res in results:
        task_id = res.get("task_id", "?")
        output: dict = {}

        # Multi-task: read the temp JSON to get the original tool output
        temp_path = res.get("file_path")
        if temp_path and Path(temp_path).exists():
            try:
                with open(temp_path, encoding="utf-8") as f:
                    output = json.load(f)
            except Exception:
                pass

        # Single-task: output is in-memory under "data"
        elif isinstance(res.get("data"), dict):
            output = res["data"]

        file_path = output.get("file_path", "")
        download_url = output.get("original_download_url", "")

        if file_path or download_url:
            lines.append(f"**任务 {task_id}**")
            if file_path:
                lines.append(f"- 文件路径：`{file_path}`")
            if download_url:
                lines.append(f"- 下载地址：[点击下载]({download_url})")

    if not lines:
        return ""
    return "#### 数据文件\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def insight_node(
    state: AgentState,
    default_prompts: dict | None = None,
) -> dict:
    """Generate the final answer and emit THREE separate ANSWER_DELTA messages:
       Part1 — Analysis text (LLM stream)
       Part2 — Data tables  (one block)
       Part3 — File info    (one block)
    """
    logger.debug("insight_node: synthesising final answer …")

    messages = state.get("messages", [])
    context = state.get("gateway_context")
    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    # ── clarify / chat path ─────────────────────────────────────────────────
    if state.get("clarify_needed"):
        intent = state.get("intent", "未匹配到具体查询意图")
        if context is not None:
            await context.emit_chunk(
                StreamChunkEvent(content="意图澄清与对话"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_title.value,
            )
            await context.emit_chunk(
                StreamChunkEvent(content=f"识别为闲聊或未明确数据意图：{intent}"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_text.value,
            )
        sys_prompt = prompts_overwrite.get(
            "clarify_prompt",
            (
            f"你是一个高级数据分析管家。\n"
            f"检测到用户的问题可能不在我们的业务查询范围内，或者意图不清晰"
            f"（系统内部识别意图：{intent}）。\n"
            f"请以高情商、友好的助手口吻回复用户，婉拒无关闲聊，"
            f"告知你仅负责企业风险查证、账单流水分发、销售数据查询等专业业务查询，"
            f"并引导用户在授权范围内重新提问。"
            )
        )
        # Stream clarify response (single part, no tables/files)
        analysis_text = ""
        async for chunk in llm.astream(messages + [SystemMessage(content=sys_prompt)]):
            if chunk.content:
                analysis_text += chunk.content
                if context is not None:
                    await context.emit_chunk(
                        StreamChunkEvent(content=chunk.content),
                        event_type=EventType.ANSWER_DELTA.value,
                        content_type=SseMessageType.text.value,
                    )
        return {"messages": [AIMessage(content=analysis_text)]}

    # ── aggregate & format all results ──────────────────────────────────────
    raw_results = state.get("results", [])
    aggregated_data: list[dict[str, Any]] = []
    for res in raw_results:
        item = _aggregate_result(res)
        if item is not None:
            aggregated_data.append(item)

    # ── push thinking event ─────────────────────────────────────────────────
    plan = state.get("plan", [])
    if context is not None and aggregated_data:
        task_map = {t["id"]: t.get("description", "") for t in plan}
        lines = [
            f"■ {item.get('task_id', '?')}：{task_map.get(item.get('task_id', '?'), '')}\n"
            f"  → {str(item.get('data', ''))[:200]}"
            for item in aggregated_data
        ]
        thinking = f"共 {len(aggregated_data)} 个任务已完成：\n" + "\n".join(lines)
        await context.emit_chunk(
            StreamChunkEvent(content="数据分析"),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        await context.emit_chunk(
            StreamChunkEvent(content=thinking),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
        )

    # Pre-build Part2 and Part3 (needed for both Fix4 and LLM paths)
    tables_md = _extract_tables_md(aggregated_data)
    file_info_md = _extract_file_info_md(raw_results)

    # ── 单任务且已拿到结构化结果时，跳过 LLM，直接返回数据块 ────────
    if (
        len(aggregated_data) == 1
        and len(plan) == 1
        and plan[0].get("status") == "done"
        and tables_md
    ):
        logger.debug("insight_node: single structured-result task — skipping LLM.")
        history_parts: list[str] = []

        if tables_md and context is not None:
            await context.emit_chunk(
                StreamChunkEvent(content=tables_md),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
            history_parts.append(tables_md)

        if file_info_md and context is not None:
            await context.emit_chunk(
                StreamChunkEvent(content=file_info_md),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
            history_parts.append(file_info_md)

        return {"messages": [AIMessage(content="\n\n".join(history_parts))]}

    # ── LLM path: Part1 analysis + Part2 tables + Part3 files ───────────────

    # Give LLM a concise data description — tables will be sent separately
    data_summary = json.dumps(
        [{"task_id": item["task_id"], "summary": str(item.get("data", ""))[:300]}
         for item in aggregated_data],
        ensure_ascii=False,
    )
    default_analysis_prompt = (
        "你是一个高级数据分析师。\n"
        "以下是各子任务的数据摘要（完整数据表格将单独展示，无需在回复中重复）：\n"
        f"{data_summary}\n\n"
        "请结合原始问题，输出一段专业的自然语言分析报告。\n"
        "要求：\n"
        "1. 只输出文字分析，不要输出 Markdown 表格。\n"
        "2. 可以引用数据中的关键数字和结论。\n"
        "3. 尽量简明扼要，聚焦核心洞察。"
    )
    sys_prompt = prompts_overwrite.get("insight_prompt", default_analysis_prompt)

    # Part1: stream analysis text token by token
    analysis_text = ""
    async for chunk in llm.astream(messages + [SystemMessage(content=sys_prompt)]):
        if chunk.content:
            analysis_text += chunk.content
            if context is not None:
                await context.emit_chunk(
                    StreamChunkEvent(content=chunk.content),
                    event_type=EventType.ANSWER_DELTA.value,
                    content_type=SseMessageType.text.value,
                )

    # Part2: data tables (one block)
    if tables_md and context is not None:
        await context.emit_chunk(
            StreamChunkEvent(content=tables_md),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=SseMessageType.text.value,
        )

    # Part3: file info (one block)
    if file_info_md and context is not None:
        await context.emit_chunk(
            StreamChunkEvent(content=file_info_md),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=SseMessageType.text.value,
        )

    # Persist complete content to conversation history
    history_content = analysis_text
    if tables_md:
        history_content += f"\n\n{tables_md}"
    if file_info_md:
        history_content += f"\n\n{file_info_md}"

    return {"messages": [AIMessage(content=history_content)]}
