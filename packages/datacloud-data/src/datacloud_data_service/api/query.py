"""
REST 查询接口模块

本模块提供数据查询的 REST API 端点，包括：
- 自然语言查询接口
- 分页查询支持
- 文件查询支持

API 端点：
- POST /query: 自然语言查询
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from datacloud_data_sdk.context import InvocationContext

router = APIRouter()


def _parse_include_plan() -> bool:
    """
    解析是否在响应中包含执行计划

    从环境变量 DC_INCLUDE_PLAN_IN_RESPONSE 读取配置。

    Returns:
        bool: 是否包含计划
    """
    v = os.environ.get("DC_INCLUDE_PLAN_IN_RESPONSE", "true").lower()
    return v not in ("false", "0")


class QueryRequest(BaseModel):
    """
    查询请求模型

    Attributes:
        question: 自然语言问题
        view_id: 视图 ID
        object_ids: 对象 ID 列表
        page: 页码
        page_size: 每页大小
        file_id: 文件 ID（用于文件查询）
    """

    question: str
    view_id: str = ""
    object_ids: list[str] = []
    page: int = 1
    page_size: int = 100
    file_id: str = ""


class QueryResponse(BaseModel):
    """
    查询响应模型

    Attributes:
        code: 状态码
        message: 消息
        data: 响应数据
    """

    code: int = 0
    message: str = "success"
    data: dict[str, Any] = {}


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(body: QueryRequest, request: Request) -> QueryResponse:
    """
    自然语言查询端点

    接收自然语言问题，执行查询并返回结果。

    Args:
        body: 查询请求体
        request: FastAPI 请求对象

    Returns:
        QueryResponse: 查询结果

    Raises:
        HTTPException: 缺少必要参数时抛出
    """
    tenant_id = request.headers.get("X-Tenant-Id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")

    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        return QueryResponse(code=500, message="OntologyLoader not initialized", data={})

    if body.file_id:
        return await _query_by_file_id(body, request)

    ctx_kwargs = {
        "tenant_id": tenant_id,
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
        "system_code": request.headers.get("X-System-Code", ""),
    }

    with InvocationContext(**ctx_kwargs):
        try:
            from datacloud_data_service.tools.unified_query import UnifiedQuery

            query = UnifiedQuery(loader)
            include_plan = _parse_include_plan()
            mcp_result = await query.execute(
                question=body.question,
                view_id=body.view_id,
                object_ids=body.object_ids or None,
                include_plan=include_plan,
                page=body.page if body.page > 0 else 1,
                page_size=body.page_size if body.page_size > 0 else 100,
            )

            content = mcp_result.get("content", [{}])
            text = content[0].get("text", "{}") if content else "{}"
            try:
                sdk_result = json.loads(text)
            except json.JSONDecodeError:
                sdk_result = {"code": 500, "message": text, "data": {}}

            return QueryResponse(
                code=sdk_result.get("code", 0),
                message=sdk_result.get("message", "success"),
                data=sdk_result.get("data", {}),
            )
        except Exception as e:
            return QueryResponse(code=500, message=str(e), data={})


async def _query_by_file_id(body: QueryRequest, request: Request) -> QueryResponse:
    from datacloud_data_service.config import get_settings
    from datacloud_data_sdk.csv_storage.manager import CsvStorageManager

    settings = get_settings()
    csv_manager = CsvStorageManager(settings.csv_base_dir)
    path = csv_manager.get_export_path(body.file_id)

    if path is None or not path.exists():
        return QueryResponse(code=404, message="File not found or invalid file_id", data={})

    try:
        import csv

        page = body.page if body.page > 0 else 1
        page_size = body.page_size if body.page_size > 0 else 100
        skip_rows = (page - 1) * page_size

        stored_meta = csv_manager.get_export_meta(body.file_id)

        records = []
        total = 0

        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
            total = len(all_rows)

            start_idx = skip_rows
            end_idx = skip_rows + page_size
            paginated_rows = all_rows[start_idx:end_idx]

            for row in paginated_rows:
                records.append(dict(row))

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        file_url = stored_meta.get("file_url", "") if stored_meta else ""
        # 兼容旧格式（历史数据中可能存的是 download_url）
        if not file_url:
            file_url = stored_meta.get("download_url", "") if stored_meta else ""
        view_id = stored_meta.get("viewId", "file_view") if stored_meta else "file_view"
        trace_data = stored_meta.get("trace", {}) if stored_meta else {}

        meta = {
            "viewId": view_id,
            "columns": stored_meta.get("columns", []) if stored_meta else [],
            "total": total,
            "overflow": stored_meta.get("overflow", False) if stored_meta else False,
            "preview_rows": preview_rows,
            "file_id": body.file_id,
        }

        overflow_notice = ""
        if meta["overflow"] and file_url:
            overflow_notice = (
                f"【重要】数据量较大（共 {total} 条），此处仅返回前 {len(records)} 条预览。"
                f"完整数据请通过以下文件路径获取：{file_url}"
            )

        response_data: dict[str, Any] = {
            "result_type": "normal",
            "records": records,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "meta": meta,
        }

        if file_url:
            response_data["file"] = {"file_url": file_url, "file_id": body.file_id}
        if overflow_notice:
            response_data["overflow_notice"] = overflow_notice
        if trace_data:
            response_data["trace"] = trace_data

        return QueryResponse(
            code=0,
            message="success",
            data=response_data,
        )
    except Exception as e:
        return QueryResponse(code=500, message=str(e), data={})
