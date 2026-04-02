from __future__ import annotations
import csv
import io
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_CHUNK_ROWS = 100  # 每个 6001 chunk 携带的行数

async def format_result(
    react_final: dict[str, Any],
    gateway_context: Any,
    workspace_dir: str | None = None,
) -> None:
    result_type = react_final.get("result_type", "text")
    if result_type == "csv_file":
        csv_path = react_final.get("csv_file_path", "")
        if not csv_path:
            await _emit_text(gateway_context, "（CSV 路径为空，无法输出）")
            return
        resolved = Path(csv_path)
        if not resolved.is_absolute() and workspace_dir:
            resolved = Path(workspace_dir) / csv_path
        if not resolved.exists():
            await _emit_text(gateway_context, f"（CSV 文件不存在: {csv_path}）")
            return
        await _stream_csv_as_6001(gateway_context, resolved)
    elif result_type == "json":
        data = react_final.get("data")
        if data is None:
            await _emit_text(gateway_context, "（JSON 数据为空）")
            return
        await _emit_json_as_6001(gateway_context, data)
    elif result_type == "json_file":
        # execute_code 执行后将 _result 保存到同名 .json 文件
        # data_query overflow 时保存到 CSV 文件（file_url）
        # LLM 可用 result_type=json_file + csv_file_path 指向该文件
        json_path = react_final.get("csv_file_path", "")
        if not json_path:
            await _emit_text(gateway_context, "（JSON 文件路径为空）")
            return
        resolved = Path(json_path)
        if not resolved.is_absolute() and workspace_dir:
            resolved = Path(workspace_dir) / json_path
        if not resolved.exists():
            await _emit_text(gateway_context, f"（文件不存在: {json_path}）")
            return
        # 根据扩展名选择读取方式
        if resolved.suffix.lower() == ".csv":
            await _stream_csv_as_6001(gateway_context, resolved)
        else:
            try:
                with open(resolved, encoding="utf-8") as f:
                    data = json.load(f)
                await _emit_json_as_6001(gateway_context, data)
            except Exception as exc:
                logger.error("format_result json_file read failed: %s", exc)
                await _emit_text(gateway_context, f"（读取 JSON 文件失败: {exc}）")
    else:
        answer = react_final.get("answer", "")
        await _emit_text(gateway_context, answer)

async def _emit_text(gateway_context: Any, text: str) -> None:
    if gateway_context is None:
        return
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
        from by_framework.core.protocol.content_type import SseMessageType  # type: ignore
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=text),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=SseMessageType.text.value,
        )
    except Exception as exc:
        logger.warning("format_result: emit_text failed: %s", exc)

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
            from by_framework.core.protocol.content_type import SseMessageType as SMT  # type: ignore
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
            from by_framework.core.protocol.content_type import SseMessageType as SMT  # type: ignore
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
