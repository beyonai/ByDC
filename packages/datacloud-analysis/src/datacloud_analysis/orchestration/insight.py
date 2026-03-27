"""④ Summary and reply generation (design §3.1 INSIGHT).

Responsibilities
----------------
- Collect outputs from all completed sub-tasks (from state results or workspace).
- Format structured query results as Markdown tables; format code_exec results from _result.
- Emit results in ANSWER_DELTA messages:
    Part1 — Analysis report  (LLM-generated text, streamed token by token)
    Part2+Part3 — Merged JSON envelope (code/message/data) with records, pagination,
                  meta, optional file, notice_msg; content_type=data_table_json (6001).
- For legacy non-structured outputs, Part2/Part3 fall back to Markdown text blocks.
- For single structured-result tasks, skip LLM and emit Part1 omitted + JSON block.
- ``notice_msg`` may append ``original_download_url`` or ``file_path`` when not already present.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseMessageType, SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage

from datacloud_analysis.orchestration.query_shape_utils import count_rows_like_envelope_build
from datacloud_analysis.orchestration.state import AgentState

# 6001：结构化数据表 JSON；旧版 gateway_sdk 无枚举成员时回退为字面量
_SSE_DATA_TABLE_JSON = getattr(SseMessageType, "data_table_json", None)
CONTENT_TYPE_DATA_TABLE_JSON = (
    _SSE_DATA_TABLE_JSON.value if _SSE_DATA_TABLE_JSON is not None else "6001"
)

logger = logging.getLogger(__name__)


async def _emit_reasoning_log_end_before_answer(context: Any) -> None:
    """Emit ``reasoningLogEnd`` before any ``answerDelta`` (SSE: 推理结束 → 答案).

    Gateway previously sent this after the graph finished, which reversed order
    with insight-node streaming. The contract is: end reasoning first, then answer.
    """
    if context is None:
        return
    await context.emit_chunk(
        StreamChunkEvent(content="思考完成"),
        event_type=EventType.REASONING_LOG_END.value,
        content_type=SseReasonMessageType.think_title.value,
    )


def _append_task_prompt_to_system(
    prompts_overwrite: dict[str, Any],
    base_system_prompt: str,
) -> str:
    """Append Agent ``task_prompt`` (e.g. processingFlow from Init plugin) to insight LLM system text.

    When ``insight_prompt`` / ``clarify_prompt`` are set, this still appends at the end so
    task-level constraints (处理流程等) are not dropped.

    Args:
        prompts_overwrite: ``state["prompts_overwrite"]`` from gateway AgentConfig.
        base_system_prompt: The system prompt built for this path (clarify or Part1).

    Returns:
        ``base_system_prompt`` with a non-empty ``task_prompt`` section appended, or unchanged.
    """
    task_extra = prompts_overwrite.get("task_prompt")
    if task_extra is None:
        return base_system_prompt
    extra = str(task_extra).strip()
    if not extra:
        return base_system_prompt
    return (
        base_system_prompt.rstrip()
        + "\n\n## 数字员工任务约束（来自 Agent 配置）\n"
        + extra
    )


def _safe_int(value: Any, default: int) -> int:
    """Coerce meta numeric fields to int; avoid crashing on bad upstream types."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


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
    total = (
        _safe_int(meta.get("total"), len(records))
        if isinstance(meta, dict)
        else len(records)
    )

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


_UUID_IN_PATH = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def _load_raw_output_dict(res: dict) -> dict[str, Any]:
    """Load the original tool output dict from workspace JSON or in-memory data."""
    temp_path = res.get("file_path")
    if temp_path and Path(temp_path).exists():
        try:
            with open(temp_path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    data = res.get("data")
    if isinstance(data, dict):
        return data
    return {}


def _records_shaped_output(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalised {records, meta, file_path, ...} or None.

    Row-count rules for logging/reconcile must stay aligned with
    :func:`datacloud_analysis.orchestration.query_shape_utils.count_rows_like_envelope_build`.
    """
    if not isinstance(output, dict):
        return None
    if "records" in output and "meta" in output:
        return output
    if "preview" in output and "columns" in output:
        preview = output.get("preview", [])
        return {
            "records": preview,
            "meta": {
                "objectId": output.get("objectId", ""),
                "objectName": output.get("objectName", ""),
                "columns": output.get("columns", []),
                "total": output.get("total", len(preview) if isinstance(preview, list) else 0),
            },
            "file_path": output.get("file_path", ""),
            "original_download_url": output.get("original_download_url", ""),
            "overflow_notice": output.get("overflow_notice", ""),
        }
    return None


def _normalize_column_meta(col: Any) -> dict[str, str]:
    """Map one column descriptor to {name, label, type}."""
    if isinstance(col, dict):
        name = str(col.get("name", col.get("label", ""))).strip()
        label = str(col.get("label", col.get("name", name))).strip()
        typ = str(col.get("type", "string")).strip() or "string"
        return {"name": name, "label": label, "type": typ}
    if isinstance(col, str):
        return {"name": col, "label": col, "type": "string"}
    return {"name": "", "label": "", "type": "string"}


def _pagination_from_meta(meta: dict[str, Any], records: list[Any]) -> dict[str, Any]:
    """Build pagination block from meta + current record slice."""
    total = _safe_int(meta.get("total"), len(records))
    page = max(1, _safe_int(meta.get("page"), 1))
    if meta.get("page_size") is not None:
        page_size = max(1, _safe_int(meta.get("page_size"), 1))
    else:
        page_size = max(len(records), 1) if records else 1
    total_pages = max(1, (total + page_size - 1) // page_size)
    has_next = page < total_pages
    has_prev = page > 1
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_prev": has_prev,
    }


def _file_block_from_paths(file_path: str, download_url: str) -> dict[str, str] | None:
    """Build file {file_url, file_id} when any path is present."""
    if not file_path and not download_url:
        return None
    file_id = ""
    for candidate in (file_path, download_url):
        if not candidate:
            continue
        m = _UUID_IN_PATH.search(candidate)
        if m:
            file_id = m.group(1)
            break
    file_url = file_path or download_url
    return {"file_url": file_url, "file_id": file_id}


def _default_notice_msg(meta: dict[str, Any], records: list[Any], overflow: str) -> str:
    if overflow.strip():
        return overflow.strip()
    total = _safe_int(meta.get("total"), len(records))
    if total > len(records):
        return (
            f"【重要】数据量较大（共 {total} 条），此处仅返回前 {len(records)} 条预览。"
        )
    return ""


def _enrich_notice_with_download(
    notice: str,
    file_path: str,
    download_url: str,
) -> str:
    """Append download hint when upstream did not put URL in overflow_notice.

    Prefers HTTP(S) ``original_download_url``; if only ``file_path`` is set, append path hint.
    """
    url = (download_url or "").strip()
    if url and url not in notice:
        suffix = f"完整数据请通过以下地址下载 CSV：{url}"
        if not notice.strip():
            return f"【重要】{suffix}"
        return f"{notice}\n{suffix}"

    path = (file_path or "").strip()
    if path and path not in notice and not url:
        hint = f"完整数据文件路径：{path}"
        if not notice.strip():
            return f"【重要】{hint}"
        return f"{notice}\n{hint}"

    return notice


def build_structured_data_envelope(
    raw_results: list[dict[str, Any]],
    *,
    result_type: str = "normal",
) -> dict[str, Any] | None:
    """Build {code, message, data} for SSE content_type 6001, or None if no query shape.

    Merges ``records`` across tasks that expose records+meta (or preview+columns).
    ``meta`` / ``pagination`` / column definitions come **only from the first** such task;
    if multiple tasks use different schemas, merged rows may not match that meta — callers
    with multi-task flows should prefer one query task or extend this logic.

    File path / download URL / overflow notice prefer the first non-empty values from raw
    results. After building ``notice_msg``, HTTP download URL or file path is appended when
    still missing from the text (see :func:`_enrich_notice_with_download`).

    Args:
        raw_results: Entries from ``state["results"]`` (in-memory ``data`` and/or temp JSON path).
        result_type: ``normal`` / ``rejected`` / ``ask_user`` when wired from upstream.

    Returns:
        Envelope ``{code, message, data}`` for SSE, or ``None`` when no query-shaped output exists.
    """
    merged_records: list[Any] = []
    meta_base: dict[str, Any] | None = None
    file_path = ""
    download_url = ""
    notice_overflow = ""
    found = False

    for res in raw_results:
        out = _load_raw_output_dict(res)
        shaped = _records_shaped_output(out)
        if not shaped:
            continue
        found = True
        recs = shaped.get("records", [])
        if isinstance(recs, list):
            merged_records.extend(recs)
        if meta_base is None:
            meta_base = shaped.get("meta") if isinstance(shaped.get("meta"), dict) else {}
        if not file_path:
            file_path = str(out.get("file_path", "") or "")
        if not download_url:
            download_url = str(out.get("original_download_url", "") or "")
        if not notice_overflow:
            notice_overflow = str(out.get("overflow_notice", "") or "")

    if not found:
        return None

    # First shaped task always assigns meta_base; keep a dict for type safety
    meta_base = meta_base or {}

    columns_raw = meta_base.get("columns", [])
    if not isinstance(columns_raw, list):
        columns_raw = []
    columns_norm = [_normalize_column_meta(c) for c in columns_raw]
    if not any(c.get("name") for c in columns_norm) and merged_records:
        first_row = merged_records[0]
        if isinstance(first_row, dict):
            columns_norm = [
                {"name": str(k), "label": str(k), "type": "string"} for k in first_row.keys()
            ]

    notice_base = _default_notice_msg(meta_base, merged_records, notice_overflow)
    fb = _file_block_from_paths(file_path, download_url)
    notice_final = _enrich_notice_with_download(notice_base, file_path, download_url)

    data_inner: dict[str, Any] = {
        "result_type": result_type,
        "records": merged_records,
        "pagination": _pagination_from_meta(meta_base, merged_records),
        "meta": {
            "objectId": meta_base.get("objectId", ""),
            "objectName": meta_base.get("objectName", ""),
            "columns": columns_norm,
        },
        "notice_msg": notice_final,
    }
    if fb:
        data_inner["file"] = fb

    return {"code": 0, "message": "success", "data": data_inner}


def _log_reconcile_raw_results_vs_sse(
    raw_results: list[dict[str, Any]],
    envelope: dict[str, Any],
) -> None:
    """Log whether per-task shaped row counts sum to ``data.records`` (same rules as 6001 merge)."""
    per_task: list[str] = []
    merged = 0
    for res in raw_results:
        tid = str(res.get("task_id", "?"))
        out = _load_raw_output_dict(res)
        n = count_rows_like_envelope_build(out)
        if n is not None:
            merged += n
            per_task.append("%s=%d" % (tid, n))
        else:
            per_task.append("%s=na" % tid)
    data = envelope.get("data")
    sse_n: int | None = None
    if isinstance(data, dict):
        recs = data.get("records")
        sse_n = len(recs) if isinstance(recs, list) else None
    if sse_n is None:
        logger.warning(
            "[reconcile] cannot read sse record count; per_task=%s",
            per_task,
        )
        return
    ok = merged == sse_n
    if ok:
        logger.info(
            "[reconcile] ok merge_total_shaped_rows=%d sse_data.records=%d per_task=%s",
            merged,
            sse_n,
            per_task,
        )
    else:
        logger.warning(
            "[reconcile] MISMATCH merge_total_shaped_rows=%d sse_data.records=%d per_task=%s",
            merged,
            sse_n,
            per_task,
        )


def _log_user_facing_6001(
    envelope: dict[str, Any],
    raw_results: list[dict[str, Any]] | None = None,
) -> None:
    """Log what will be pushed to the user as SSE 6001 (counts/meta, not cell values)."""
    data = envelope.get("data")
    if not isinstance(data, dict):
        logger.info(
            "[user SSE 6001] envelope_missing_data keys=%s",
            list(envelope.keys()),
        )
        return
    recs = data.get("records")
    n = len(recs) if isinstance(recs, list) else None
    pag = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    cols = meta.get("columns")
    n_cols = len(cols) if isinstance(cols, list) else None
    first_keys = ""
    if isinstance(recs, list) and recs and isinstance(recs[0], dict):
        first_keys = ",".join(list(recs[0].keys())[:16])
    task_ids = [str(r.get("task_id", "?")) for r in (raw_results or [])]
    logger.info(
        "[user SSE 6001] result_task_ids=%s objectId=%s objectName=%s records=%s pagination=%s "
        "column_count=%s first_row_field_sample=%s notice_len=%d",
        task_ids,
        meta.get("objectId", ""),
        meta.get("objectName", ""),
        n,
        pag,
        n_cols,
        first_keys,
        len(str(data.get("notice_msg", "") or "")),
    )


async def _emit_part2_part3(
    context: Any,
    raw_results: list[dict[str, Any]],
    tables_md: str,
    file_info_md: str,
    *,
    envelope: dict[str, Any] | None = None,
) -> str:
    """Emit merged JSON (6001) when query-shaped results exist; else Markdown Part2+Part3.

    Returns the same string stored in conversation history (JSON or Markdown).
    """
    if envelope is None:
        envelope = build_structured_data_envelope(raw_results)
    if envelope is not None:
        _log_reconcile_raw_results_vs_sse(raw_results, envelope)
        _log_user_facing_6001(envelope, raw_results)
        text = json.dumps(envelope, ensure_ascii=False)
        logger.info(
            "[user SSE 6001] json_bytes=%d (same payload as answerDelta content)",
            len(text.encode("utf-8")),
        )
        if context is not None:
            await context.emit_chunk(
                StreamChunkEvent(content=text),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=CONTENT_TYPE_DATA_TABLE_JSON,
            )
        return text

    text = "\n\n".join([x for x in (tables_md, file_info_md) if x])
    logger.info(
        "[user SSE text] no 6001 envelope; tables_md_len=%d file_info_md_len=%d combined_len=%d",
        len(tables_md),
        len(file_info_md),
        len(text),
    )
    if context is not None:
        if tables_md:
            await context.emit_chunk(
                StreamChunkEvent(content=tables_md),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
        if file_info_md:
            await context.emit_chunk(
                StreamChunkEvent(content=file_info_md),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
    return text


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def insight_node(
    state: AgentState,
    default_prompts: dict | None = None,
) -> dict:
    """Generate the final answer: Part1 LLM stream, then Part2+Part3 as one JSON (6001) or Markdown."""
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
        await _emit_reasoning_log_end_before_answer(context)
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
        sys_prompt = _append_task_prompt_to_system(prompts_overwrite, sys_prompt)
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
        logger.info(
            "[user SSE text] clarify path: answer_delta_total_chars=%d",
            len(analysis_text),
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
    structured_envelope = build_structured_data_envelope(raw_results)

    await _emit_reasoning_log_end_before_answer(context)

    # ── 单任务且已拿到结构化结果时，跳过 LLM，直接返回数据块 ────────
    if (
        len(aggregated_data) == 1
        and len(plan) == 1
        and plan[0].get("status") == "done"
        and (tables_md or structured_envelope is not None)
    ):
        logger.debug("insight_node: single structured-result task — skipping LLM.")
        part23 = await _emit_part2_part3(
            context,
            raw_results,
            tables_md,
            file_info_md,
            envelope=structured_envelope,
        )
        logger.info(
            "[user SSE summary] single-task fast path: part23_only_chars=%d (6001 or markdown inside)",
            len(part23),
        )
        return {"messages": [AIMessage(content=part23)]}

    # ── LLM path: Part1 analysis + Part2+Part3 as one 6001 JSON or Markdown ─

    # Concise per-task summary; full rows go in the following SSE JSON (6001), not here
    data_summary = json.dumps(
        [{"task_id": item["task_id"], "summary": str(item.get("data", ""))[:300]}
         for item in aggregated_data],
        ensure_ascii=False,
    )
    default_analysis_prompt = (
        "你是一个高级数据分析师。\n"
        "以下是各子任务的数据摘要。完整查询结果（records、分页、文件与提示等）会在同一会话中"
        "以独立消息推送（content_type=6001 的 JSON 数据块），请勿在正文中重复整张表或逐行列出。\n"
        f"{data_summary}\n\n"
        "请结合原始问题，输出一段专业的自然语言分析报告。\n"
        "要求：\n"
        "1. 只输出文字分析，不要输出 Markdown 表格。\n"
        "2. 可以引用数据中的关键数字和结论。\n"
        "3. 尽量简明扼要，聚焦核心洞察。"
    )
    sys_prompt = prompts_overwrite.get("insight_prompt", default_analysis_prompt)
    sys_prompt = _append_task_prompt_to_system(prompts_overwrite, sys_prompt)

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

    part23 = await _emit_part2_part3(
        context,
        raw_results,
        tables_md,
        file_info_md,
        envelope=structured_envelope,
    )
    logger.info(
        "[user SSE summary] main path: part1_text_chars=%d part23_chars=%d",
        len(analysis_text),
        len(part23),
    )

    # Persist complete content to conversation history
    history_content = analysis_text
    if part23:
        history_content += f"\n\n{part23}"

    return {"messages": [AIMessage(content=history_content)]}
