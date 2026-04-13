"""
查询/动作结果格式化模块

将 SDK 原始查询/动作执行结果格式化为标准 data 结构。
当数据量超过阈值时，自动保存完整数据到 CSV 文件，
并在返回的 data 中填写 file.file_url（本地文件路径）。

SDK 层只返回 data 内容（flat 格式）：
    {
        "result_type": "normal",
        "records": [...],
        "pagination": {...},   # 仅 overflow 时有
        "meta": {...},
        "file": {"file_url": "/path/to/file.csv", "file_id": "uuid"},  # 仅 overflow 时有
        "overflow_notice": "...",  # 仅 overflow 时有
        "trace": {...},
        "plan": {...},             # 仅 include_plan=True 时有
    }

service 层负责包装 {code, message, data}。
"""

from __future__ import annotations

from math import ceil
from typing import Any


def build_query_response(
    raw_result: dict[str, Any],
    *,
    csv_manager: Any,
    threshold: int = 10,
    preview_rows: int = 5,
) -> dict[str, Any]:
    """
    将原始查询结果格式化为标准 data 结构。

    当 threshold > 0 且 records 数量超过阈值时：
    - 完整数据写入 CSV 文件（exports/）
    - data.records 仅保留前 preview_rows 行
    - data.file.file_url 为 CSV 文件本地路径
    - data.pagination 描述分页信息
    - data.overflow_notice 给出提示

    Args:
        raw_result: SDK 查询返回的原始字典，含 records / meta / trace / plan(可选)
        csv_manager: CsvStorageManager 实例
        threshold: 超过该行数才触发 overflow（0 = 不限制）
        preview_rows: overflow 时返回的预览行数

    Returns:
        标准 data 结构字典
    """
    records: list[dict[str, Any]] = raw_result.get("records") or []
    meta: dict[str, Any] = dict(raw_result.get("meta") or {})
    trace: dict[str, Any] = raw_result.get("trace") or {}
    plan: Any = raw_result.get("plan")

    total = len(records)
    meta["total"] = total

    data: dict[str, Any] = {
        "result_type": "normal",
        "records": records,
        "total": total,
        "meta": meta,
        "trace": trace,
    }
    if plan is not None:
        data["plan"] = plan

    if threshold > 0 and total > threshold:
        # meta["columns"] 可能是字符串列表（ViewLookupExecutor / _normalize_to_unified_format
        # 生成的原始字段码）或字典列表（{"name": ..., "label": ...}），需兼容两种格式
        columns = [
            ((c.get("name") or c.get("label")) if isinstance(c, dict) else c)
            for c in meta.get("columns", [])
            if ((c.get("name") or c.get("label")) if isinstance(c, dict) else c)
        ]
        if not columns and records:
            columns = list(records[0].keys())

        export_meta: dict[str, Any] = {
            "columns": meta.get("columns", []),
            "overflow": True,
            "preview_rows": preview_rows,
            "viewId": meta.get("viewId") or meta.get("objectId", ""),
            "trace": trace,
        }
        file_id, file_path = csv_manager.save_export(
            records, columns=columns or None, meta=export_meta
        )

        preview = records[:preview_rows]
        total_pages = ceil(total / preview_rows) if preview_rows > 0 else 0

        data["records"] = preview
        data["pagination"] = {
            "page": 1,
            "page_size": preview_rows,
            "total": total,
            "total_pages": total_pages,
            "has_next": total > preview_rows,
            "has_prev": False,
        }
        data["meta"] = {
            **meta,
            "overflow": True,
            "preview_rows": len(preview),
        }
        data["file"] = {
            "file_url": str(file_path),
            "file_id": file_id,
        }
        data["overflow_notice"] = (
            f"【重要】数据量较大（共 {total} 条），此处仅返回前 {len(preview)} 条预览。"
            f"完整数据请通过以下文件路径获取：{file_path}"
        )

    return data


def build_error_data(
    message: str,
    result_type: str = "rejected",
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    构建错误 data 结构（service 层负责包装 code/message）。

    Args:
        message: 错误信息
        result_type: 结果类型（rejected / ask_user）
        trace: 追踪信息

    Returns:
        标准 data 结构字典
    """
    return {
        "result_type": result_type,
        "overflow_notice": message,
        "trace": trace or {},
    }
