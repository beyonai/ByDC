from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)
_CHUNK_ROWS = 100


def _get_output_format() -> str:
    """Return output format configured by DATACLOUD_OUTPUT_FORMAT."""
    return os.environ.get("DATACLOUD_OUTPUT_FORMAT", "markdown").lower().strip()


def _data_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
    """Render tabular data as Markdown."""
    if not columns:
        return ""

    def _escape_cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(_escape_cell(c) for c in columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, separator]
    for row in rows:
        cells = [_escape_cell(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _query_result_headers_and_record_keys(
    query_data: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Resolve display headers and record keys from query_result payload."""
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
            keys.append(record_key)
            headers.append(display or record_key)
        elif isinstance(col, str) and col.strip():
            token = col.strip()
            keys.append(token)
            headers.append(token)

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


def _normalize_rows(columns: list[str], raw_rows: Any) -> list[list[str]]:
    """Normalize heterogeneous rows into a matrix of strings."""
    if not isinstance(raw_rows, list):
        return []
    normalized: list[list[str]] = []
    for row in raw_rows:
        if isinstance(row, Mapping):
            normalized.append([str(row.get(col, "")) for col in columns])
        elif isinstance(row, (list, tuple)):
            normalized.append([str(value) for value in row])
        else:
            normalized.append([str(row)])
    return normalized


def _load_json_file(path: Path) -> Any:
    with open(path, encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _load_csv_rows(path: Path) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as file_obj:
        reader = csv.reader(file_obj)
        return list(reader)


async def format_result(
    react_final: dict[str, Any],
    gateway_context: Any,
    workspace_dir: str | None = None,
) -> None:
    """Format and emit final ReAct result."""
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
        answer = react_final.get("answer", "")
        query_data = react_final.get("query_data")

        if answer and not answer_was_streamed and not query_data:
            await _emit_text(gateway_context, str(answer))
        if not query_data:
            if not answer:
                await _emit_text(gateway_context, "(query_data 为空)")
            return

        if output_fmt == "markdown":
            # answer 已流式推送时跳过原始数据表格，避免重复推送
            if not answer_was_streamed:
                await _emit_query_result_as_markdown(gateway_context, query_data)
        else:
            await _emit_query_result_as_6001(gateway_context, query_data)
        return

    if result_type == "csv_file":
        csv_path = react_final.get("csv_file_path", "")
        if not csv_path:
            await _emit_text(gateway_context, "(CSV 路径为空，无法输出)")
            return

        resolved = _resolve_result_path(csv_path, workspace_dir)
        if not resolved.exists():
            await _emit_text(gateway_context, f"(CSV 文件不存在: {csv_path})")
            return

        if output_fmt == "markdown":
            await _stream_csv_as_markdown(gateway_context, resolved)
        else:
            await _stream_csv_as_6001(gateway_context, resolved)
        return

    if result_type == "json":
        data = react_final.get("data")
        if data is None:
            await _emit_text(gateway_context, "(JSON 数据为空)")
            return

        if output_fmt == "markdown":
            await _emit_json_as_markdown(gateway_context, data)
        else:
            await _emit_json_as_6001(gateway_context, data)
        return

    if result_type == "json_file":
        json_path = react_final.get("csv_file_path") or react_final.get("json_file_path") or ""
        if not json_path:
            await _emit_text(gateway_context, "(JSON 文件路径为空)")
            return

        resolved = _resolve_result_path(json_path, workspace_dir)
        if not resolved.exists():
            await _emit_text(gateway_context, f"(文件不存在: {json_path})")
            return

        if resolved.suffix.lower() == ".csv":
            if output_fmt == "markdown":
                await _stream_csv_as_markdown(gateway_context, resolved)
            else:
                await _stream_csv_as_6001(gateway_context, resolved)
            return

        try:
            data = await asyncio.to_thread(_load_json_file, resolved)
        except Exception as exc:  # noqa: BLE001
            logger.error("format_result json_file read failed: %s", exc)
            await _emit_text(gateway_context, f"(读取 JSON 文件失败: {exc})")
            return

        if output_fmt == "markdown":
            await _emit_json_as_markdown(gateway_context, data)
        else:
            await _emit_json_as_6001(gateway_context, data)
        return

    answer = react_final.get("answer", "")
    if not answer_was_streamed:
        await _emit_text(gateway_context, answer)


async def _emit_text(gateway_context: Any, text: str) -> None:
    if gateway_context is None:
        return

    try:
        from by_framework import EventType, StreamChunkEvent
        from by_framework.core.protocol.content_type import SseMessageType

        await gateway_context.emit_chunk(
            StreamChunkEvent(content=coerce_stream_chunk_text(text)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=SseMessageType.text.value,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("format_result: emit_text failed: %s", exc)


async def _emit_json_as_markdown(gateway_context: Any, data: Any) -> None:
    """Emit arbitrary JSON-like payload as markdown table."""
    if isinstance(data, str):
        with suppress(Exception):
            data = json.loads(data)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        columns = list(data[0].keys())
        rows = [[str(row.get(col, "")) for col in columns] for row in data]
    elif isinstance(data, dict) and "columns" in data and "data" in data:
        raw_columns = data["columns"]
        columns = [str(col) for col in raw_columns] if isinstance(raw_columns, list) else []
        rows = _normalize_rows(columns, data["data"])
    elif isinstance(data, list):
        columns = ["result"]
        rows = [[str(item)] for item in data]
    else:
        columns = ["result"]
        rows = [[json.dumps(data, ensure_ascii=False, default=str)]]

    markdown_text = _data_to_markdown(columns, rows)
    await _emit_text(gateway_context, markdown_text)


async def _stream_csv_as_markdown(gateway_context: Any, csv_path: Path) -> None:
    try:
        rows = await asyncio.to_thread(_load_csv_rows, csv_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("_stream_csv_as_markdown read failed: %s", exc)
        await _emit_text(gateway_context, f"(读取 CSV 文件失败: {exc})")
        return

    if not rows:
        return

    header = rows[0]
    data_rows = rows[1:]
    markdown_text = _data_to_markdown(header, data_rows)
    await _emit_text(gateway_context, markdown_text)


async def _emit_query_result_as_markdown(gateway_context: Any, query_data: dict[str, Any]) -> None:
    columns, record_keys = _query_result_headers_and_record_keys(query_data)
    records = query_data.get("records") or []

    if isinstance(records, list) and records and isinstance(records[0], dict) and record_keys:
        rows = [[str(record.get(key, "")) for key in record_keys] for record in records]
    else:
        rows = [[str(record)] for record in records]

    notice = query_data.get("notice_msg") or query_data.get("overflow_notice") or ""
    markdown_text = _data_to_markdown(columns, rows)
    if notice:
        markdown_text = markdown_text + "\n\n> " + str(notice)

    await _emit_text(gateway_context, markdown_text)


async def _emit_json_as_6001(gateway_context: Any, data: Any) -> None:
    if gateway_context is None:
        return

    try:
        from by_framework import EventType, StreamChunkEvent
    except ImportError:
        logger.warning("by_framework not available, skipping 6001 json emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import SseMessageType

            content_type_candidate = getattr(SseMessageType, "data_table_json", None)
            if content_type_candidate is not None:
                content_type_6001 = content_type_candidate.value
        except Exception:  # noqa: BLE001
            pass

        if isinstance(data, str):
            with suppress(Exception):
                data = json.loads(data)

        if isinstance(data, list) and data and isinstance(data[0], dict):
            columns = list(data[0].keys())
            rows = [[str(row.get(col, "")) for col in columns] for row in data]
        elif isinstance(data, dict) and "columns" in data and "data" in data:
            raw_columns = data["columns"]
            columns = [str(col) for col in raw_columns] if isinstance(raw_columns, list) else []
            rows = _normalize_rows(columns, data["data"])
        elif isinstance(data, list):
            columns = ["result"]
            rows = [[str(item)] for item in data]
        else:
            columns = ["result"]
            rows = [[json.dumps(data, ensure_ascii=False, default=str)]]

        total_chunks = max(1, (len(rows) + _CHUNK_ROWS - 1) // _CHUNK_ROWS)
        for seq, start in enumerate(range(0, max(1, len(rows)), _CHUNK_ROWS), 1):
            chunk_rows = rows[start : start + _CHUNK_ROWS]
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
    except Exception as exc:  # noqa: BLE001
        logger.error("_emit_json_as_6001 failed: %s", exc)


async def _stream_csv_as_6001(gateway_context: Any, csv_path: Path) -> None:
    if gateway_context is None:
        return

    try:
        from by_framework import EventType, StreamChunkEvent
    except ImportError:
        logger.warning("by_framework not available, skipping 6001 emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import SseMessageType

            content_type_candidate = getattr(SseMessageType, "data_table_json", None)
            if content_type_candidate is not None:
                content_type_6001 = content_type_candidate.value
        except Exception:  # noqa: BLE001
            pass

        rows = await asyncio.to_thread(_load_csv_rows, csv_path)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:]
        total_chunks = max(1, (len(data_rows) + _CHUNK_ROWS - 1) // _CHUNK_ROWS)

        for seq, start in enumerate(range(0, max(1, len(data_rows)), _CHUNK_ROWS), 1):
            chunk_rows = data_rows[start : start + _CHUNK_ROWS]
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
    except Exception as exc:  # noqa: BLE001
        logger.error("_stream_csv_as_6001 failed: %s", exc)


async def _emit_query_result_as_6001(gateway_context: Any, query_data: dict[str, Any]) -> None:
    if gateway_context is None:
        return

    try:
        from by_framework import EventType, StreamChunkEvent
    except ImportError:
        logger.warning("by_framework not available, skipping query_result emit")
        return

    try:
        content_type_6001 = "6001"
        try:
            from by_framework.core.protocol.content_type import SseMessageType

            content_type_candidate = getattr(SseMessageType, "data_table_json", None)
            if content_type_candidate is not None:
                content_type_6001 = content_type_candidate.value
        except Exception:  # noqa: BLE001
            pass

        meta_raw = query_data.get("meta")
        meta: Mapping[str, Any] = meta_raw if isinstance(meta_raw, Mapping) else {}

        columns_raw = meta.get("columns", [])
        columns_norm: list[dict[str, str]] = []
        if isinstance(columns_raw, list):
            for col in columns_raw:
                if isinstance(col, Mapping):
                    name = str(col.get("name") or col.get("label") or "")
                    label = str(col.get("label") or col.get("name") or name)
                    col_type = str(col.get("type") or "string")
                    columns_norm.append({"name": name, "label": label, "type": col_type})
                elif isinstance(col, str):
                    columns_norm.append({"name": col, "label": col, "type": "string"})

        records = query_data.get("records") or []
        if (
            not columns_norm
            and isinstance(records, list)
            and records
            and isinstance(records[0], dict)
        ):
            columns_norm = [{"name": key, "label": key, "type": "string"} for key in records[0]]

        payload: dict[str, Any] = {
            "result_type": query_data.get("result_type", "normal"),
            "records": records,
            "pagination": query_data.get("pagination") or _build_pagination(records, meta),
            "meta": {
                "objectId": meta.get("objectId", ""),
                "objectName": meta.get("objectName", ""),
                "columns": columns_norm,
            },
            "notice_msg": query_data.get("notice_msg") or query_data.get("overflow_notice") or "",
        }
        if query_data.get("file"):
            payload["file"] = query_data["file"]

        text = json.dumps(payload, ensure_ascii=False, default=str)
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=coerce_stream_chunk_text(text)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=content_type_6001,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("_emit_query_result_as_6001 failed: %s", exc)


def _build_pagination(records: list[Any], meta: Mapping[str, Any] | None) -> dict[str, Any]:
    total = int((meta or {}).get("total", len(records)))
    page_size = max(len(records), 1)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "page": 1,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": total_pages > 1,
        "has_prev": False,
    }
