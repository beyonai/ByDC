"""RPC handler for 'query' service.

Replicates the logic of POST /api/v1/query (query_routes.py).
Uses get_request_loader_snapshot(request) to access the loader runtime.
"""

from __future__ import annotations

import csv
import json
import logging
from typing import TYPE_CHECKING, Any

import anyio
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.i18n import (
    format_loader_not_initialized,
    format_overflow_notice,
    format_tenant_id_required,
    translate_exception,
)
from fastapi import Request

from datacloud_platform.config import get_settings
from datacloud_platform.models.common import ok
from datacloud_platform.loader_runtime import get_request_loader_snapshot

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)
_INCLUDE_PLAN_IN_RESPONSE = False


def _request_language(request: Request) -> str:
    return request.headers.get("X-Language", request.headers.get("Accept-Language", ""))


def _build_context_kwargs(request: Request) -> dict[str, Any]:
    return {
        "tenant_id": request.headers.get("X-Tenant-Id", ""),
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "")
        .removeprefix("Bearer ")
        .strip(),
        "system_code": request.headers.get("X-System-Code", ""),
        "language": _request_language(request),
    }


def _load_csv_rows_from_text(content: str) -> list[dict[str, str]]:
    return [dict(row) for row in csv.DictReader(content.splitlines())]


async def _query_execute(
    platform: DatacloudPlatform, params: dict[str, Any], request: Request
) -> Any:
    tenant_id = request.headers.get("X-Tenant-Id", "")
    language = _request_language(request)
    if not tenant_id:
        raise ValueError(format_tenant_id_required(language))

    snapshot = await get_request_loader_snapshot(request, reason="rest_query")
    if snapshot is None:
        return ok(code=500, message=format_loader_not_initialized(language), data={})

    loader = snapshot.loader

    question: str = params.get("question", "")
    view_id: str = params.get("view_id", "")
    object_ids: list[str] = params.get("object_ids", [])
    knowledge_context: str | None = params.get("knowledge_context")
    file_id: str = params.get("file_id", "")
    page = max(int(params.get("page", 1)), 1)
    page_size = max(int(params.get("page_size", 100)), 1)

    if file_id:
        return await _query_by_file_id(file_id, page, page_size, request, snapshot)

    ctx_kwargs = _build_context_kwargs(request)
    with InvocationContext(**ctx_kwargs):
        try:
            from datacloud_platform.execution.unified_query import UnifiedQuery

            query = UnifiedQuery(loader)
            mcp_result = await query.execute(
                question=question,
                view_id=view_id,
                object_ids=object_ids or None,
                knowledge_context=knowledge_context,
                include_plan=_INCLUDE_PLAN_IN_RESPONSE,
                page=page,
                page_size=page_size,
            )

            content = mcp_result.get("content", [{}])
            text = content[0].get("text", "{}") if content else "{}"
            try:
                sdk_result = json.loads(text)
            except json.JSONDecodeError:
                sdk_result = {"code": 500, "message": text, "data": {}}

            return ok(
                code=sdk_result.get("code", 0),
                message=sdk_result.get("message", "success"),
                data=sdk_result.get("data", {}),
            )
        except Exception as e:
            return ok(code=500, message=translate_exception(e, language), data={})


async def _query_by_file_id(
    file_id: str,
    page: int,
    page_size: int,
    request: Request,
    snapshot: Any,
) -> Any:
    settings = get_settings()
    loader = snapshot.loader
    result_file_storage = getattr(
        getattr(loader, "_config", None), "result_file_storage", None
    )
    language = _request_language(request)
    with InvocationContext(**_build_context_kwargs(request)):
        csv_manager = CsvStorageManager(
            settings.csv_base_dir,
            result_file_storage=result_file_storage,
        )
        csv_content = csv_manager.read_export_csv(file_id)
        stored_meta = csv_manager.get_export_meta(file_id)

    if csv_content is None:
        from datacloud_data_sdk.i18n import format_file_not_found

        return ok(code=404, message=format_file_not_found(language), data={})

    try:
        skip_rows = (page - 1) * page_size
        all_rows = await anyio.to_thread.run_sync(_load_csv_rows_from_text, csv_content)
        total = len(all_rows)
        records = all_rows[skip_rows : skip_rows + page_size]

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        file_url = (
            stored_meta.get("file_url", "") or stored_meta.get("download_url", "")
            if stored_meta
            else ""
        )
        view_id = stored_meta.get("viewId", "file_view") if stored_meta else "file_view"
        trace_data = stored_meta.get("trace", {}) if stored_meta else {}
        preview_rows = (
            stored_meta.get("preview_rows", len(records))
            if stored_meta
            else len(records)
        )

        meta = {
            "viewId": view_id,
            "columns": stored_meta.get("columns", []) if stored_meta else [],
            "total": total,
            "overflow": stored_meta.get("overflow", False) if stored_meta else False,
            "preview_rows": preview_rows,
            "file_id": file_id,
        }

        overflow_notice = ""
        if meta["overflow"] and file_url:
            overflow_notice = format_overflow_notice(
                language=language,
                total=total,
                preview_count=len(records),
                file_path=file_url,
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
            response_data["file"] = {"file_url": file_url, "file_id": file_id}
        if overflow_notice:
            response_data["overflow_notice"] = overflow_notice
        if trace_data:
            response_data["trace"] = trace_data

        return ok(code=0, message="success", data=response_data)
    except Exception as e:
        return ok(code=500, message=translate_exception(e, language), data={})


REGISTRY: dict[str, Any] = {
    "execute": _query_execute,
}
