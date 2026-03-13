"""MCP Streamable HTTP 实现（基于官方 mcp SDK）。

参考 datacloud_mcp_server 使用 StreamableHTTPSessionManager + Server。
采用 stateless + SSE 格式（json_response=False），符合 MCP Streamable HTTP 规范。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import Resource, TextContent, Tool
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)

# 由 routes lifespan 注入，用于在 MCP handler 中获取 loader
_loader_ref: Any = None


def set_loader_ref(ref: Any) -> None:
    """设置 loader 引用，供 list_tools/call_tool 使用。"""
    global _loader_ref
    _loader_ref = ref


def _get_loader():
    loader = _loader_ref() if callable(_loader_ref) else _loader_ref
    return loader


def _create_mcp_app() -> tuple[Server, StreamableHTTPSessionManager]:
    """创建 MCP Server 和 StreamableHTTPSessionManager。"""
    server = Server("datacloud-data-service")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """动态返回工具列表，基于 OntologyLoader。"""
        try:
            loader = _get_loader()
            if loader is None:
                return [_unified_query_tool_fallback()]
            from datacloud_data_sdk.context import get_tool_list_mode
            from datacloud_data_service.tools.registry import ToolRegistry

            registry = ToolRegistry(loader)
            tool_list_mode = get_tool_list_mode()
            tools_raw = registry.list_tools(tool_list_mode=tool_list_mode)
            result: list[Tool] = []
            for t in tools_raw:
                t.pop("_meta", None)
                result.append(
                    Tool(
                        name=t["name"],
                        title=t.get("title"),
                        description=t.get("description", ""),
                        inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
                    )
                )
            return result
        except Exception as e:
            logger.exception("list_tools failed: %s", e)
            return [_unified_query_tool_fallback()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """执行工具调用。"""
        try:
            loader = _get_loader()
            if loader is None:
                return [TextContent(type="text", text=json.dumps({"error": "OntologyLoader not initialized"}, ensure_ascii=False))]

            if name == "unified_data_query":
                from datacloud_data_service.tools.unified_query import UnifiedQuery

                query = UnifiedQuery(loader)
                result = await query.execute(
                    question=arguments.get("question", ""),
                    view_id=arguments.get("view_id", ""),
                    object_ids=arguments.get("object_ids"),
                )
                text = result["content"][0]["text"] if result.get("content") else "{}"
                return [TextContent(type="text", text=text)]

            object_code = _find_action_object(loader, name)
            if object_code is None:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False))]
            from datacloud_data_service.tools.action_executor import ActionExecutor

            term_loader = getattr(loader._config, "term_loader", None)
            executor = ActionExecutor(loader, term_loader=term_loader)
            result = await executor.execute(object_code, name, arguments)
            text = result.get("content", [{}])[0].get("text", "{}") if result.get("content") else "{}"
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.exception("call_tool failed: %s", e)
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """返回资源列表，当前为空列表。"""
        return []

    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=False,  # 使用 SSE 格式，符合 MCP Streamable HTTP 规范
        stateless=True,
    )
    return server, session_manager


def _unified_query_tool_fallback() -> Tool:
    return Tool(
        name="unified_data_query",
        title="统一数据查询",
        description="通过自然语言查询数据",
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "自然语言查询问题"},
                "view_id": {"type": "string", "description": "视图ID"},
                "object_ids": {"type": "array", "items": {"type": "string"}, "description": "对象ID列表"},
            },
            "required": ["question"],
        },
    )


def _find_action_object(loader: Any, action_code: str) -> str | None:
    for cls in loader.get_ontology_classes():
        for action in cls.actions:
            if action.action_code == action_code:
                return cls.object_code
    return None


def create_mcp_session_manager() -> StreamableHTTPSessionManager:
    """创建 MCP Server 和 StreamableHTTPSessionManager。返回 session_manager，需在 lifespan 中 run()。"""
    _, sm = _create_mcp_app()
    return sm


def _headers_from_scope(scope: Scope) -> dict[str, str]:
    """从 ASGI scope 提取 headers 为小写 key 的 dict。"""
    raw = scope.get("headers") or []
    return {k.decode().lower(): v.decode() for k, v in raw}


def create_mcp_asgi_app(session_manager: StreamableHTTPSessionManager):
    """创建 MCP 的 ASGI 应用，供 Mount 挂载。session_manager.run() 需在父 app lifespan 中调用。"""

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        from datacloud_data_sdk.context import InvocationContext

        headers = _headers_from_scope(scope)
        auth = headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else ""
        tool_mode = headers.get("x-tool-list-mode", "unified")
        if tool_mode not in ("unified", "per_object"):
            tool_mode = "per_object"
        ctx_kwargs = {
            "tenant_id": headers.get("x-tenant-id", ""),
            "user_id": headers.get("x-user-id", ""),
            "session_id": headers.get("x-session-id", ""),
            "token": token,
            "system_code": headers.get("x-system-code", ""),
            "tool_list_mode": tool_mode,
        }
        try:
            with InvocationContext(**ctx_kwargs):
                await session_manager.handle_request(scope, receive, send)
        except Exception as e:
            logger.exception("MCP request failed: %s", e)
            from starlette.responses import JSONResponse

            resp = JSONResponse({"error": str(e)}, status_code=500)
            await resp(scope, receive, send)

    return handle_streamable_http
