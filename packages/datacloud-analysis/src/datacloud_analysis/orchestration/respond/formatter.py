from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)
_CHUNK_ROWS = 100  # 每个 6001 chunk 携带的行数


def _get_output_format() -> str:
    """读取 DATACLOUD_OUTPUT_FORMAT 环境变量，返回 'markdown' 或 'json'，默认 markdown。"""
    return os.environ.get("DATACLOUD_OUTPUT_FORMAT", "markdown").lower().strip()


def _data_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
    """将列名和行数据渲染为 Markdown 表格字符串。"""
    if not columns:
        return ""
    escape = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    header = "| " + " | ".join(escape(c) for c in columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, separator]
    for row in rows:
        cells = [escape(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _query_result_headers_and_record_keys(query_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """从 ``meta.columns`` 解析 Markdown 表头与 ``records`` 行字典的取值键。

    - **取值键**：与 ``records[i]`` 中 dict 的 key 一致；优先 ``field_code`` / ``code``，
      再 ``name`` / ``field``（与 query_executor 等约定 ``name``=字段编码 一致）。
    - **表头**：优先人类可读名（``label`` / ``field_name`` / ``property_name`` 等），
      避免仅有 ``name``=字段编码时把表头也显示成编码。
    """

    meta = query_data.get("meta") or {}
    columns_raw = meta.get("columns", []) if isinstance(meta, dict) else []
    headers: list[str] = []
    keys: list[str] = []
    for col in columns_raw:
        if isinstance(col, dict):
            record_key = str(
                col.get("field_code")
                or col.get("code")
                or col.get("name")
                or col.get("field")
                or ""
            ).strip()
            display = str(
                col.get("label")
                or col.get("title")
                or col.get("field_name")
                or col.get("property_name")
                or col.get("displayName")
                or col.get("display_name")
                or ""
            ).strip()
            if not record_key:
                continue
            header = display or record_key
            keys.append(record_key)
            headers.append(header or record_key)
        elif isinstance(col, str) and col.strip():
            s = col.strip()
            keys.append(s)
            headers.append(s)

    records = query_data.get("records") or []
    if not keys and isinstance(records, list) and records and isinstance(records[0], dict):
        keys = list(records[0].keys())
        headers = list(keys)

    return headers, keys


def _resolve_result_path(path_str: str, workspace_dir: str | None) -> Path:
    resolved = Path(path_str)
    if not resolved.is_absolute() and workspace_dir:
        workspace_root_raw = resolve_shared_workspace_dir(workspace_dir)
        if workspace_root_raw is not None:
            resolved = Path(str(workspace_root_raw)) / path_str
    return resolved

async def format_result(
    react_final: dict[str, Any],
    gateway_context: Any,
    workspace_dir: str | None = None,
) -> None:
    result_type = react_final.get("result_type", "text")
    answer_was_streamed = bool(react_final.get("answer_streamed", False))
    output_fmt = _get_output_format()
    logger.info(
        "[format_result] result_type=%s has_query_data=%s answer_streamed=%s output_format=%s",
        result_type,
        bool(react_final.get("query_data")),
        answer_was_streamed,
        output_fmt,
    )
    if result_type == "query_result":
        # data_query 原始结构透传：{result_type, records, pagination, meta, file, notice_msg}
        # query_result 优先结构化输出；避免口述 JSON
        answer = react_final.get("answer", "")
        query_data = react_final.get("query_data")
        if answer and not answer_was_streamed and not query_data:
            await _emit_text(gateway_context, str(answer))
        if not query_data:
            if not answer:
                await _emit_text(gateway_context, "（query_data 为空）")
            return
        if output_fmt == "markdown":
            await _emit_query_result_as_markdown(gateway_context, query_data)
        else:
            await _emit_query_result_as_6001(gateway_context, query_data)
    elif result_type == "csv_file":
        csv_path = react_final.get("csv_file_path", "")
        if not csv_path:
            await _emit_text(gateway_context, "（CSV 路径为空，无法输出）")
            return
        resolved = _resolve_result_path(csv_path, workspace_dir)
        if not resolved.exists():
            await _emit_text(gateway_context, f"（CSV 文件不存在: {csv_path}）")
            return
        if output_fmt == "markdown":
            await _stream_csv_as_markdown(gateway_context, resolved)
        else:
            await _stream_csv_as_6001(gateway_context, resolved)
    elif result_type == "json":
        data = react_final.get("data")
        if data is None:
            await _emit_text(gateway_context, "（JSON 数据为空）")
            return
        if output_fmt == "markdown":
            await _emit_json_as_markdown(gateway_context, data)
        else:
            await _emit_json_as_6001(gateway_context, data)
    elif result_type == "json_file":
        # execute_code 执行后将 _result 保存到同名 .json 文件
        # data_query overflow 时保存到 CSV 文件（file_url）
        # LLM 可用 result_type=json_file + csv_file_path 指向该文件
        json_path = react_final.get("csv_file_path", "")
        if not json_path:
            await _emit_text(gateway_context, "（JSON 文件路径为空）")
            return
        resolved = _resolve_result_path(json_path, workspace_dir)
        if not resolved.exists():
            await _emit_text(gateway_context, f"（文件不存在: {json_path}）")
            return
        # 根据扩展名选择读取方式
        if resolved.suffix.lower() == ".csv":
            if output_fmt == "markdown":
                await _stream_csv_as_markdown(gateway_context, resolved)
            else:
                await _stream_csv_as_6001(gateway_context, resolved)
        else:
            try:
                with open(resolved, encoding="utf-8") as f:
                    data = json.load(f)
                if output_fmt == "markdown":
                    await _emit_json_as_markdown(gateway_context, data)
                else:
                    await _emit_json_as_6001(gateway_context, data)
            except Exception as exc:
                logger.error("format_result json_file read failed: %s", exc)
                await _emit_text(gateway_context, f"（读取 JSON 文件失败: {exc}）")
    else:
        answer = react_final.get("answer", "")
        if not answer_was_streamed:
            await _emit_text(gateway_context, answer)

async def _emit_text(gateway_context: Any, text: str) -> None:
    if gateway_context is None:
        return
    # [DIAG] 诊断日志：追踪每次 text 推送的内容和调用栈
    import traceback as _tb
    _caller = "".join(_tb.format_stack(limit=4)[-3:-1]).replace("\n", " | ")
    logger.warning("[_emit_text DIAG] len=%d preview=%r caller=%s", len(text), text[:120], _caller)
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
        from by_framework.core.protocol.content_type import SseMessageType  # type: ignore
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=coerce_stream_chunk_text(text)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=SseMessageType.text.value,
        )
    except Exception as exc:
        logger.warning("format_result: emit_text failed: %s", exc)


async def _emit_json_as_markdown(gateway_context: Any, data: Any) -> None:
    """将 JSON 数据渲染为 Markdown 表格后通过 text 通道推送。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            pass

    if isinstance(data, list) and data and isinstance(data[0], dict):
        columns = list(data[0].keys())
        rows = [[str(row.get(col, "")) for col in columns] for row in data]
    elif isinstance(data, dict) and "columns" in data and "data" in data:
        columns = list(data["columns"])
        rows = [list(r) for r in data["data"]]
    elif isinstance(data, list):
        columns = ["result"]
        rows = [[str(item)] for item in data]
    else:
        columns = ["result"]
        rows = [[json.dumps(data, ensure_ascii=False, default=str)]]

    md = _data_to_markdown(columns, rows)
    await _emit_text(gateway_context, md)


async def _stream_csv_as_markdown(gateway_context: Any, csv_path: Path) -> None:
    """将 CSV 文件渲染为 Markdown 表格后通过 text 通道推送。"""
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except Exception as exc:
        logger.error("_stream_csv_as_markdown read failed: %s", exc)
        await _emit_text(gateway_context, f"（读取 CSV 文件失败: {exc}）")
        return

    if not rows:
        return
    header = rows[0]
    data_rows = rows[1:]
    md = _data_to_markdown(header, data_rows)
    await _emit_text(gateway_context, md)


async def _emit_query_result_as_markdown(gateway_context: Any, query_data: dict[str, Any]) -> None:
    """将 data_query 返回的原始 data block 渲染为 Markdown 表格后通过 text 通道推送。"""
    columns, record_keys = _query_result_headers_and_record_keys(query_data)
    records = query_data.get("records") or []

    # [DIAG] 诊断日志
    logger.warning(
        "[_emit_query_result_as_markdown DIAG] records_n=%d columns=%s first_record=%s",
        len(records),
        columns[:5],
        str(records[0])[:120] if records else "N/A",
    )

    if isinstance(records, list) and records and isinstance(records[0], dict):
        rows = [[str(r.get(k, "")) for k in record_keys] for r in records]
    else:
        rows = [[str(r)] for r in records]

    notice = query_data.get("notice_msg") or query_data.get("overflow_notice") or ""
    md = _data_to_markdown(columns, rows)
    if notice:
        md = md + "\n\n> " + str(notice)
    await _emit_text(gateway_context, md)

async def _emit_json_as_6001(gateway_context: Any, data: Any) -> None:
    """将工具返回的 JSON 数据转换为 6001 格式推送。

    data 可以是：
    - str：先尝试 json.loads 解析
    - list[dict]：直接提取列名和行数据
    - dict with 'columns'/'data' keys：直接使用
    - 其他：包装为单行单列
    """
    if gateway_context is None:
        return
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
    except ImportError:
        logger.warning("by_framework not available, skipping 6001 json emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import (
                SseMessageType as SMT,  # type: ignore
            )
            ct = getattr(SMT, "data_table_json", None)
            if ct is not None:
                content_type_6001 = ct.value
        except Exception:
            pass

        # 如果 data 是字符串，尝试解析为 JSON 对象
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass  # 保持原始字符串，后续走 else 分支包装为单列

        # 规范化为 columns + rows 格式
        if isinstance(data, list) and data and isinstance(data[0], dict):
            columns = list(data[0].keys())
            rows = [[str(row.get(col, "")) for col in columns] for row in data]
        elif isinstance(data, dict) and "columns" in data and "data" in data:
            columns = list(data["columns"])
            rows = [list(r) for r in data["data"]]
        elif isinstance(data, list):
            columns = ["result"]
            rows = [[str(item)] for item in data]
        else:
            columns = ["result"]
            rows = [[json.dumps(data, ensure_ascii=False, default=str)]]

        total_chunks = max(1, (len(rows) + _CHUNK_ROWS - 1) // _CHUNK_ROWS)
        for seq, start in enumerate(range(0, max(1, len(rows)), _CHUNK_ROWS), 1):
            chunk_rows = rows[start: start + _CHUNK_ROWS]
            payload = {
                "type": 6001,
                "seq": seq,
                "total": total_chunks,
                "columns": columns,
                "data": chunk_rows,
            }
            await gateway_context.emit_chunk(
                StreamChunkEvent(content=json.dumps(payload, ensure_ascii=False)),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=content_type_6001,
            )
    except Exception as exc:
        logger.error("_emit_json_as_6001 failed: %s", exc)


async def _stream_csv_as_6001(gateway_context: Any, csv_path: Path) -> None:
    if gateway_context is None:
        return
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
        from by_framework.core.protocol.content_type import SseMessageType  # type: ignore
    except ImportError:
        logger.warning("by_framework not available, skipping 6001 emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import (
                SseMessageType as SMT,  # type: ignore
            )
            ct = getattr(SMT, "data_table_json", None)
            if ct is not None:
                content_type_6001 = ct.value
        except Exception:
            pass

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:]
        total_chunks = max(1, (len(data_rows) + _CHUNK_ROWS - 1) // _CHUNK_ROWS)

        for seq, start in enumerate(range(0, max(1, len(data_rows)), _CHUNK_ROWS), 1):
            chunk_rows = data_rows[start: start + _CHUNK_ROWS]
            payload = {
                "type": 6001,
                "seq": seq,
                "total": total_chunks,
                "columns": header,
                "data": chunk_rows,
            }
            await gateway_context.emit_chunk(
                StreamChunkEvent(content=json.dumps(payload, ensure_ascii=False)),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=content_type_6001,
            )
    except Exception as exc:
        logger.error("_stream_csv_as_6001 failed: %s", exc)


async def _emit_query_result_as_6001(gateway_context: Any, query_data: dict[str, Any]) -> None:
    """将 data_query 返回的原始 data block 按旧格式整体推送一次 6001 SSE。

    推送结构（与旧代码 build_structured_data_envelope 保持一致）：
    {result_type, records, pagination, meta, file, notice_msg}
    """
    if gateway_context is None:
        return

    # [DIAG] 诊断日志
    _recs = query_data.get("records") or []
    logger.warning(
        "[_emit_query_result_as_6001 DIAG] records_n=%d first_record=%s",
        len(_recs),
        str(_recs[0])[:120] if _recs else "N/A",
    )

    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
    except ImportError:
        logger.warning("by_framework not available, skipping query_result emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import (
                SseMessageType as SMT,  # type: ignore
            )
            ct = getattr(SMT, "data_table_json", None)
            if ct is not None:
                content_type_6001 = ct.value
        except Exception:
            pass

        # 规范化 columns：确保 {name, label, type} 格式
        meta = query_data.get("meta") or {}
        columns_raw = meta.get("columns", []) if isinstance(meta, dict) else []
        columns_norm = []
        for col in columns_raw:
            if isinstance(col, dict):
                name = str(col.get("name") or col.get("label") or "")
                label = str(col.get("label") or col.get("name") or name)
                typ = str(col.get("type") or "string")
                columns_norm.append({"name": name, "label": label, "type": typ})
            elif isinstance(col, str):
                columns_norm.append({"name": col, "label": col, "type": "string"})

        # 如果 columns 为空但 records 有数据，从第一行推断
        records = query_data.get("records") or []
        if not columns_norm and isinstance(records, list) and records and isinstance(records[0], dict):
            columns_norm = [{"name": k, "label": k, "type": "string"} for k in records[0]]

        payload: dict[str, Any] = {
            "result_type": query_data.get("result_type", "normal"),
            "records": records,
            "pagination": query_data.get("pagination") or _build_pagination(records, meta),
            "meta": {
                "objectId": meta.get("objectId", "") if isinstance(meta, dict) else "",
                "objectName": meta.get("objectName", "") if isinstance(meta, dict) else "",
                "columns": columns_norm,
            },
            "notice_msg": query_data.get("notice_msg") or query_data.get("overflow_notice") or "",
        }
        if query_data.get("file"):
            payload["file"] = query_data["file"]

        text = json.dumps(payload, ensure_ascii=False, default=str)
        logger.info("[query_result 6001] records=%d has_file=%s bytes=%d",
                    len(records), bool(payload.get("file")), len(text.encode("utf-8")))
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=coerce_stream_chunk_text(text)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=content_type_6001,
        )
    except Exception as exc:
        logger.error("_emit_query_result_as_6001 failed: %s", exc)


def _build_pagination(records: list, meta: dict) -> dict[str, Any]:
    """从 meta 或 records 长度构建分页信息。"""
    total = int(meta.get("total", len(records))) if isinstance(meta, dict) else len(records)
    page_size = max(len(records), 1) if records else 1
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "page": 1,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": total_pages > 1,
        "has_prev": False,
    }
