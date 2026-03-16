"""CSV 导出文件下载接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from datacloud_data_service.config import get_settings
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager

router = APIRouter()


@router.get("/download/csv/{file_id}")
async def download_csv(file_id: str) -> FileResponse:
    """下载查询结果导出的 CSV 文件。"""
    settings = get_settings()
    csv_manager = CsvStorageManager(settings.csv_base_dir)
    path = csv_manager.get_export_path(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found or invalid file_id")
    return FileResponse(
        path=path,
        media_type="text/csv",
        filename=f"query_result_{file_id[:8]}.csv",
    )
