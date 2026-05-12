"""MCP JSON-RPC 2.0 handler。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.context import InvocationContext, get_current_context
from datacloud_data_sdk.i18n import (
    format_loader_not_initialized,
    format_method_not_found,
    format_unknown_tool,
    format_use_post_for_jsonrpc,
    translate_exception,
)
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def _parse_object_ids_header(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _request_language(request: Request) -> str:
    return request.headers.get("X-Language", request.headers.get("Accept-Language", ""))


def _extract_context(request: Request) -> dict[str, Any]:
    tenant_id = request.headers.get("X-Tenant-Id", "")
    tool_mode = request.headers.get("X-Tool-List-Mode", "unified")
    if tool_mode not in ("unified", "per_object"):
        tool_mode = "unified"
    view_ids = _parse_object_ids_header(request.headers.get("X-View-Ids", ""))
    view_id = request.headers.get("X-View-Id", "").strip() or (view_ids[0] if view_ids else "")
    object_ids = _parse_object_ids_header(request.headers.get("X-Object-Ids", ""))
    object_id = request.headers.get("X-Object-Id", "").strip()
    if object_id:
        object_ids = [object_id]
    return {
        "tenant_id": tenant_id,
        "user_id": request.headers.get("X-User-Id", ""),
        "session_id": request.headers.get("X-Session-Id", ""),
        "token": request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
        "system_code": request.headers.get("X-System-Code", ""),
        "tool_list_mode": tool_mode,
        "view_id": view_id,
        "object_ids": object_ids or None,
        "language": _request_language(request),
    }


def _jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


@router.get("/mcp")
@router.get("/mcp/")
async def mcp_get_not_supported(request: Request) -> JSONResponse:
    """Streamable HTTP：本服务不提供 GET/SSE 流，客户端应直接 POST。返回 405 供客户端识别。"""
    return JSONResponse(
        status_code=405,
        content={"detail": format_use_post_for_jsonrpc(_request_language(request))},
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
            language = get_current_context().language
            return JSONResponse(
                _jsonrpc_error(
                    rpc_id,
                    -32601,
                    format_method_not_found(language, method),
                )
            )


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
                "name": "datacloud-data",
                "version": "0.1.0",
            },
        },
    }


def _get_tools_list(request: Request) -> list[dict]:
    """从 OntologyLoader 动态生成工具列表。"""
    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        return [_fallback_unified_query_tool()]

    from datacloud_data_sdk.context import get_current_context

    from datacloud_data_service.tools.registry import ToolRegistry

    registry = ToolRegistry(loader)
    ctx = get_current_context()
    tools = registry.list_tools(
        view_id=ctx.view_id or None,
        object_ids=ctx.object_ids,
        tool_list_mode=ctx.tool_list_mode,
    )
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
            "content": [
                {
                    "type": "text",
                    "text": format_loader_not_initialized(get_current_context().language),
                }
            ],
            "isError": True,
        }

    if tool_name == "unified_data_query":
        from datacloud_data_service.tools.unified_query import UnifiedQuery

        query = UnifiedQuery(loader)
        return await query.execute(
            question=arguments.get("question", ""),
            view_id=arguments.get("view_id", ""),
            object_ids=arguments.get("object_ids"),
            knowledge_context=arguments.get("knowledge_context"),
        )

    object_code = _find_action_object(loader, tool_name)
    if object_code is None:
        language = get_current_context().language
        return {
            "content": [
                {
                    "type": "text",
                    "text": format_unknown_tool(language, tool_name),
                }
            ],
            "isError": True,
        }

    from datacloud_data_service.tools.action_executor import ActionExecutor

    executor = ActionExecutor(loader)
    try:
        return await executor.execute(object_code, tool_name, arguments)
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": translate_exception(e, get_current_context().language)}
            ],
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
                "knowledge_context": {
                    "type": "string",
                    "description": "知识增强上下文，会在生成查询计划时提供给模型（可选）",
                },
            },
            "required": ["question"],
        },
    }
