"""REST 查询接口。"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from datacloud_data_sdk.context import InvocationContext

router = APIRouter()


def _parse_include_plan() -> bool:
    v = os.environ.get("DC_INCLUDE_PLAN_IN_RESPONSE", "true").lower()
    return v not in ("false", "0")


class QueryRequest(BaseModel):
    question: str
    view_id: str = ""
    object_ids: list[str] = []


class QueryResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict[str, Any] = {}


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(body: QueryRequest, request: Request) -> QueryResponse:
    tenant_id = request.headers.get("X-Tenant-Id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")

    ctx_kwargs = {
        "tenant_id": tenant_id,
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
        "system_code": request.headers.get("X-System-Code", ""),
    }

    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        return QueryResponse(code=500, message="OntologyLoader not initialized", data={})

    with InvocationContext(**ctx_kwargs):
        try:
            from datacloud_data_service.tools.unified_query import UnifiedQuery

            query = UnifiedQuery(loader)
            include_plan = _parse_include_plan()
            result = await query.execute(
                question=body.question,
                view_id=body.view_id,
                object_ids=body.object_ids or None,
                include_plan=include_plan,
            )

            if result.get("isError"):
                content = result.get("content", [{}])
                error_text = content[0].get("text", "Unknown error") if content else "Unknown error"
                return QueryResponse(code=500, message=error_text, data={})

            content = result.get("content", [{}])
            text = content[0].get("text", "{}") if content else "{}"
            try:
                records_data = json.loads(text)
            except json.JSONDecodeError:
                records_data = {"raw": text}

            return QueryResponse(
                code=0,
                message="success",
                data=records_data,
            )
        except Exception as e:
            return QueryResponse(code=500, message=str(e), data={})
