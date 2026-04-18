"""CSV 导出文件下载接口。"""

from __future__ import annotations

from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from datacloud_data_service.config import get_settings

router = APIRouter()


@router.get("/download/csv/{file_id}")
async def download_csv(file_id: str, request: Request) -> Response:
    """下载查询结果导出的 CSV 文件。"""
    settings = get_settings()
    loader = getattr(request.app.state, "loader", None)
    result_file_storage = getattr(getattr(loader, "_config", None), "result_file_storage", None)
    ctx_kwargs = {
        "tenant_id": request.headers.get("X-Tenant-Id", ""),
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
        "system_code": request.headers.get("X-System-Code", ""),
    }
    with InvocationContext(**ctx_kwargs):
        csv_manager = CsvStorageManager(
            settings.csv_base_dir,
            result_file_storage=result_file_storage,
        )
        content = csv_manager.read_export_csv(file_id)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found or invalid file_id")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="query_result_{file_id[:8]}.csv"'},
    )
