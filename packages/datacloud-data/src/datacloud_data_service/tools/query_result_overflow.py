"""查询结果溢出处理：数据量大时存 CSV 并提供下载，避免模型上下文超长。"""

from __future__ import annotations

from typing import Any


def apply_query_result_overflow(
    result: dict[str, Any],
    *,
    threshold: int,
    preview_rows: int,
    csv_manager: Any,
    api_base_url: str,
) -> dict[str, Any]:
    """若 records 超过阈值，则存 CSV、返回元数据+下载地址+前 N 行预览。

    返回结构包含明确提示：数据不全，仅前 N 行预览，全量需通过下载地址获取。
    """
    records = result.get("records")
    if not isinstance(records, list) or len(records) <= threshold:
        return result

    total = len(records)
    meta = result.get("meta") or {}
    columns = [c.get("name") or c.get("label") for c in meta.get("columns", [])]
    if not columns and records:
        columns = list(records[0].keys())

    file_id, _ = csv_manager.save_export(
        records,
        columns=columns if columns else None,
        meta={
            **meta,
            "total": total,
            "overflow": True,
            "preview_rows": len(preview),
            "download_url": download_url,
            "file_id": file_id,
            "trace": result.get("trace", {}),
            "plan": result.get("plan"),
        },
    )

    base = (api_base_url or "").rstrip("/")
    download_url = f"{base}/api/v1/download/csv/{file_id}" if base else f"/api/v1/download/csv/{file_id}"

    preview = records[:preview_rows]

    return {
        "records": preview,
        "total": total,
        "pagination": {
            "page": 1,
            "page_size": preview_rows,
            "total": total,
            "total_pages": (total + preview_rows - 1) // preview_rows if preview_rows > 0 else 0,
            "has_next": total > preview_rows,
            "has_prev": False,
        },
        "meta": {
            **meta,
            "total": total,
            "overflow": True,
            "preview_rows": len(preview),
            "download_url": download_url,
            "file_id": file_id,
        },
        "overflow_notice": (
            f"【重要】数据量较大（共 {total} 条），此处仅返回前 {len(preview)} 条预览。"
            f"完整数据请通过以下地址下载 CSV：{download_url}"
        ),
        **{k: v for k, v in result.items() if k not in ("records", "meta", "total")},
    }
