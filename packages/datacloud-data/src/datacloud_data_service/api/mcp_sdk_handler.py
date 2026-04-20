"""MCP Streamable HTTP 实现（基于官方 mcp SDK）。

参考 datacloud_mcp_server 使用 StreamableHTTPSessionManager + Server。
采用 stateless + SSE 格式（json_response=False），符合 MCP Streamable HTTP 规范。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_data_sdk.utils.json_utils import dump_json
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Resource, TextContent, Tool
from starlette.types import Message, Receive, Scope, Send

from datacloud_data_service.loader_runtime import (
    LoaderSnapshot,
    build_external_snapshot,
)

logger = logging.getLogger(__name__)

_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key"})

# 由 routes lifespan 注入，用于在 MCP handler 中获取 loader
_loader_ref: Any = None
_loader_runtime_ref: Any = None


def set_loader_ref(ref: Any) -> None:
    """设置 loader 引用，供 list_tools/call_tool 使用。"""
    global _loader_ref
    _loader_ref = ref


def set_loader_runtime_ref(ref: Any) -> None:
    """设置 loader runtime 引用，供 list_tools/call_tool 动态刷新。"""
    global _loader_runtime_ref
    _loader_runtime_ref = ref


def _get_loader():
    loader = _loader_ref() if callable(_loader_ref) else _loader_ref
    return loader


def _get_loader_runtime():
    runtime = _loader_runtime_ref() if callable(_loader_runtime_ref) else _loader_runtime_ref
    return runtime


async def _get_loader_snapshot(reason: str) -> LoaderSnapshot | None:
    runtime = _get_loader_runtime()
    legacy_loader = _get_loader()
    if runtime is not None:
        snapshot = await runtime.ensure_fresh(reason)
        if (
            snapshot is not None
            and legacy_loader is not None
            and legacy_loader is not snapshot.loader
            and not runtime.owns_loader(legacy_loader)
        ):
            return build_external_snapshot(legacy_loader)
        return snapshot
    if legacy_loader is None:
        return None
    return build_external_snapshot(legacy_loader)


def _parse_csv_header(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _extract_content_text(payload: dict[str, Any]) -> str:
    content = payload.get("content", [])
    return content[0].get("text", "{}") if content else "{}"


def _unwrap_sdk_payload_text(payload: dict[str, Any]) -> str:
    """MCP 层对 SDK 的 {code, message, data} envelope 做一次拆包。"""
    text = _extract_content_text(payload)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(parsed, dict) and {"code", "message", "data"} <= parsed.keys():
        return dump_json(parsed["data"])

    return text


def _log_tool_call(name: str, arguments: dict[str, Any]) -> None:
    """记录 MCP tools/call 的入参与工具名。"""
    logger.info(
        "%s",
        dump_json(
            {
                "event": "mcp_tool_call",
                "tool_name": name,
                "arguments": arguments,
            }
        ),
    )


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """对敏感请求头做脱敏后返回。"""
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key in _SENSITIVE_HEADERS and value:
            if key == "authorization" and value.lower().startswith("bearer "):
                redacted[key] = "Bearer ***"
            else:
                redacted[key] = "***"
            continue
        redacted[key] = value
    return redacted


def _parse_jsonrpc_body(body: bytes) -> dict[str, Any]:
    """解析 MCP JSON-RPC 请求体，失败时返回原始文本摘要。"""
    if not body:
        return {}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw_body": body.decode("utf-8", errors="replace")}

    if not isinstance(payload, dict):
        return {"payload": payload}

    return {
        "jsonrpc": payload.get("jsonrpc"),
        "id": payload.get("id"),
        "method": payload.get("method"),
        "params": payload.get("params"),
    }


def _log_http_request(scope: Scope, headers: dict[str, str], body: bytes) -> None:
    """记录 MCP HTTP 请求头与 JSON-RPC 入参。"""
    logger.info(
        "%s",
        dump_json(
            {
                "event": "mcp_http_request",
                "http_method": scope.get("method", ""),
                "path": scope.get("path", ""),
                "headers": _redact_headers(headers),
                "jsonrpc_request": _parse_jsonrpc_body(body),
            }
        ),
    )


def _create_mcp_app() -> tuple[Server, StreamableHTTPSessionManager]:
    """创建 MCP Server 和 StreamableHTTPSessionManager。"""
    server = Server("datacloud-data")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """动态返回工具列表，基于 OntologyLoader。"""
        try:
            snapshot = await _get_loader_snapshot("mcp_tools_list")
            if snapshot is None:
                return [_unified_query_tool_fallback()]
            loader = snapshot.loader
            from datacloud_data_sdk.context import get_current_context

            from datacloud_data_service.tools.registry import ToolRegistry

            registry = ToolRegistry(loader)
            ctx = get_current_context()
            tools_raw = registry.list_tools(
                view_id=ctx.view_id or None,
                object_ids=ctx.object_ids,
                tool_list_mode=ctx.tool_list_mode,
            )
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
            tool_arguments = arguments or {}
            _log_tool_call(name, tool_arguments)
            snapshot = await _get_loader_snapshot("mcp_tools_call")
            if snapshot is None:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": "OntologyLoader not initialized"}, ensure_ascii=False
                        ),
                    )
                ]
            loader = snapshot.loader

            if name == "unified_data_query":
                from datacloud_data_service.tools.unified_query import UnifiedQuery

                query = UnifiedQuery(loader)
                result = await query.execute(
                    question=tool_arguments.get("question", ""),
                    view_id=tool_arguments.get("view_id", ""),
                    object_ids=tool_arguments.get("object_ids"),
                    knowledge_context=tool_arguments.get("knowledge_context"),
                )
                text = _unwrap_sdk_payload_text(result)
                return [TextContent(type="text", text=text)]

            scope = _find_action_scope(loader, name, snapshot=snapshot)
            if scope is None:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False),
                    )
                ]

            scope_type, scope_code = scope
            if scope_type == "view":
                # 视图级动作：通过 View.invoke_action() 执行
                try:
                    view = loader.get_view(scope_code)
                    raw = await view.invoke_action(name, tool_arguments)
                except Exception as exc:
                    return [
                        TextContent(
                            type="text", text=json.dumps({"error": str(exc)}, ensure_ascii=False)
                        )
                    ]
                text = dump_json(raw)
                return [TextContent(type="text", text=text)]
            else:
                # 对象级动作：走原有 ActionExecutor
                from datacloud_data_service.tools.action_executor import ActionExecutor

                executor = ActionExecutor(loader)
                result = await executor.execute(scope_code, name, tool_arguments)
                text = _unwrap_sdk_payload_text(result)
                return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.exception("call_tool failed: %s", e)
            return [
                TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))
            ]

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
    )


def _find_action_object(loader: Any, action_code: str) -> str | None:
    for cls in loader.get_ontology_classes():
        for action in cls.actions:
            if action.action_code == action_code:
                return cls.object_code
    return None


def _find_action_scope(
    loader: Any,
    action_code: str,
    *,
    snapshot: LoaderSnapshot | None = None,
) -> tuple[str, str] | None:
    """
    查找 action_code 对应的 (scope_type, scope_code)。

    查找顺序：
    1. 全局 VirtualActionRegistry（优先，O(1)）
    2. 对象动作遍历（兼容非虚拟动作）
    3. 视图动作遍历
    """
    if snapshot is not None:
        route_ref = snapshot.action_routes.get(action_code)
        if route_ref is not None:
            return route_ref.scope_type, route_ref.scope_code

    # 1. 优先查 VirtualActionRegistry
    try:
        from datacloud_data_sdk.virtual_action.registry import get_registry

        route = get_registry().get(action_code)
        if route:
            return route.scope_type, route.scope_code
    except Exception:
        pass

    # 2. 对象动作遍历
    for cls in loader.get_ontology_classes():
        for action in cls.actions:
            if action.action_code == action_code:
                return "object", cls.object_code

    # 3. 视图动作遍历
    for view_id, scene in getattr(loader, "_scenes", {}).items():
        for action in scene.get("_virtual_actions", []):
            if getattr(action, "action_code", None) == action_code:
                return "view", view_id

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
        body_chunks: list[bytes] = []
        request_logged = False

        async def logging_receive() -> Message:
            nonlocal request_logged
            message = await receive()
            if message["type"] != "http.request":
                return message

            body_chunks.append(message.get("body", b""))
            if not message.get("more_body", False) and not request_logged:
                request_logged = True
                _log_http_request(scope, headers, b"".join(body_chunks))
            return message

        auth = headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else ""
        tool_mode = headers.get("x-tool-list-mode", "unified")
        if tool_mode not in ("unified", "per_object"):
            tool_mode = "unified"
        view_ids = _parse_csv_header(headers.get("x-view-ids", ""))
        view_id = headers.get("x-view-id", "").strip() or (view_ids[0] if view_ids else "")
        object_ids = _parse_csv_header(headers.get("x-object-ids", ""))
        object_id = headers.get("x-object-id", "").strip()
        if object_id:
            object_ids = [object_id]
        ctx_kwargs = {
            "tenant_id": headers.get("x-tenant-id", ""),
            "user_id": headers.get("x-user-id", ""),
            "session_id": headers.get("x-session-id", ""),
            "token": token,
            "system_code": headers.get("x-system-code", ""),
            "tool_list_mode": tool_mode,
            "view_id": view_id,
            "object_ids": object_ids or None,
        }
        try:
            with InvocationContext(**ctx_kwargs):
                await session_manager.handle_request(scope, logging_receive, send)
        except Exception as e:
            logger.exception("MCP request failed: %s", e)
            from starlette.responses import JSONResponse

            resp = JSONResponse({"error": str(e)}, status_code=500)
            await resp(scope, receive, send)

    return handle_streamable_http
