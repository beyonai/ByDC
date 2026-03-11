"""MCP JSON-RPC 2.0 handler。"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from datacloud_data_sdk.context import InvocationContext

router = APIRouter()


def _extract_context(request: Request) -> dict[str, str]:
    tenant_id = request.headers.get("X-Tenant-Id", "")
    # if not tenant_id:
        # raise HTTPException(status_code=400, detail="X-Tenant-Id header required")
    return {
        "tenant_id": tenant_id,
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
        "system_code": request.headers.get("X-System-Code", ""),
    }


def _jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


@router.get("/mcp")
@router.get("/mcp/")
async def mcp_get_not_supported() -> JSONResponse:
    """Streamable HTTP：本服务不提供 GET/SSE 流，客户端应直接 POST。返回 405 供客户端识别。"""
    return JSONResponse(
        status_code=405,
        content={"detail": "Use POST for JSON-RPC messages"},
        headers={"Allow": "POST"},
    )


@router.post("/mcp")
@router.post("/mcp/")
async def mcp_endpoint(request: Request) -> JSONResponse:
    ctx_kwargs = _extract_context(request)
    body = await request.json()
    rpc_id = body.get("id", "0")
    method = body.get("method", "")
    params = body.get("params", {})

    with InvocationContext(**ctx_kwargs):
        if method == "initialize":
            return JSONResponse(_handle_initialize(rpc_id, params))
        elif method == "notifications/initialized":
            return JSONResponse({}, status_code=202)
        elif method == "tools/list":
            tools = _get_tools_list(request)
            return JSONResponse(_jsonrpc_response(rpc_id, {"tools": tools}))
        elif method == "tools/call":
            result = await _handle_tools_call(request, params)
            return JSONResponse(_jsonrpc_response(rpc_id, result))
        else:
            return JSONResponse(_jsonrpc_error(rpc_id, -32601, f"Method not found: {method}"))


def _handle_initialize(rpc_id: Any, params: dict) -> dict:
    """处理 MCP initialize 请求，返回服务端能力与信息。"""
    client_protocol = params.get("protocolVersion", "2024-11-05")
    supported = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
    protocol_version = client_protocol if client_protocol in supported else "2024-11-05"
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": True},
            },
            "serverInfo": {
                "name": "datacloud-data-service",
                "version": "0.1.0",
            },
        },
    }


def _get_tools_list(request: Request) -> list[dict]:
    """从 OntologyLoader 动态生成工具列表。"""
    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        return [_fallback_unified_query_tool()]

    from datacloud_data_service.tools.registry import ToolRegistry

    registry = ToolRegistry(loader)
    tools = registry.list_tools()
    for t in tools:
        t.pop("_meta", None)
    return tools


async def _handle_tools_call(request: Request, params: dict) -> dict:
    """处理 tools/call 请求，路由到 SDK。"""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        return {
            "content": [{"type": "text", "text": "OntologyLoader not initialized"}],
            "isError": True,
        }

    if tool_name == "unified_data_query":
        from datacloud_data_service.tools.unified_query import UnifiedQuery

        query = UnifiedQuery(loader)
        return await query.execute(
            question=arguments.get("question", ""),
            view_id=arguments.get("view_id", ""),
            object_ids=arguments.get("object_ids"),
        )
    else:
        object_code = _find_action_object(loader, tool_name)
        if object_code is None:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            }

        from datacloud_data_service.tools.action_executor import ActionExecutor

        executor = ActionExecutor(loader)
        try:
            return await executor.execute(object_code, tool_name, arguments)
        except Exception as e:
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }


def _find_action_object(loader: Any, action_code: str) -> str | None:
    """查找某 action_code 所属的 object_code。"""
    for cls in loader.get_ontology_classes():
        for action in cls.actions:
            if action.action_code == action_code:
                return cls.object_code
    return None


def _fallback_unified_query_tool() -> dict:
    return {
        "name": "unified_data_query",
        "title": "统一数据查询",
        "description": "通过自然语言查询数据",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "自然语言查询问题"},
                "view_id": {"type": "string", "description": "视图ID"},
                "object_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "对象ID列表",
                },
            },
            "required": ["question"],
        },
    }
