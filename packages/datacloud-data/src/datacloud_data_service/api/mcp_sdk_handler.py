"""MCP Streamable HTTP 实现（基于官方 mcp SDK）。

参考 datacloud_mcp_server 使用 StreamableHTTPSessionManager + Server。
采用 stateless + SSE 格式（json_response=False），符合 MCP Streamable HTTP 规范。
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from datacloud_data_sdk.context import get_current_language
from datacloud_data_sdk.i18n import (
    format_input_validation_error,
    format_loader_not_initialized,
    format_unknown_tool,
    translate_exception,
)
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
_TOOL_CALL_DETAIL_HEADER = "x-tool-call-detail"
_FALSE_HEADER_VALUES = frozenset({"0", "false", "no", "off"})

# 由 routes lifespan 注入，用于在 MCP handler 中获取 loader
_loader_ref: Any = None
_loader_runtime_ref: Any = None


class _McpGatewayContext:
    """将 MCP SSE notification 适配为 SDK GatewayProgressReporter 可消费的上下文。"""

    def __init__(self, session: Any, request_id: str) -> None:
        self._session = session
        self.message_id = request_id
        self._related_request_id = request_id

    def generate_message_id(self) -> str:
        return uuid4().hex

    async def emit_state(
        self,
        content: str,
        *,
        message_id: str = "",
        parent_message_id: str = "",
        event_type: str = "",
        content_type: str = "",
    ) -> None:
        await self._send_notification(
            {
                "event": "tool_call_step",
                "phase": "state",
                "content": content,
                "message_id": message_id,
                "parent_message_id": parent_message_id,
                "event_type": event_type,
                "content_type": content_type,
            }
        )

    async def emit_chunk(
        self,
        content: str,
        *,
        message_id: str = "",
        parent_message_id: str = "",
        event_type: str = "",
        content_type: str = "",
    ) -> None:
        await self._send_notification(
            {
                "event": "tool_call_step",
                "phase": "chunk",
                "content": content,
                "message_id": message_id,
                "parent_message_id": parent_message_id,
                "event_type": event_type,
                "content_type": content_type,
            }
        )

    @asynccontextmanager
    async def sub_step(self, title: str):
        message_id = self.generate_message_id()
        parent_message_id = self.message_id
        await self.emit_state(title, message_id=message_id, parent_message_id=parent_message_id)
        yield message_id, parent_message_id

    async def _send_notification(self, payload: dict[str, Any]) -> None:
        await self._session.send_log_message(
            level="info",
            data=payload,
            logger="datacloud_data_service.mcp",
            related_request_id=self._related_request_id,
        )


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


def _parse_bool_header(raw: str | None) -> bool:
    """解析布尔 header；未传返回 False，传入且非 false-like 值返回 True。"""
    if raw is None:
        return False
    return raw.strip().lower() not in _FALSE_HEADER_VALUES


def _strip_intermediate_fields(data: Any) -> Any:
    """默认模式下移除 tool_call 明细字段，仅保留最终结果。"""
    if not isinstance(data, dict):
        return data

    sanitized = dict(data)
    sanitized.pop("plan", None)
    sanitized.pop("execution_steps", None)
    return sanitized


def _render_tool_call_text(payload: dict[str, Any], *, include_detail: bool) -> str:
    """按 header 开关渲染 tool_call 返回文本。"""
    if include_detail:
        return _extract_content_text(payload)

    text = _unwrap_sdk_payload_text(payload)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    return dump_json(_strip_intermediate_fields(parsed))


def _build_sdk_envelope_text(data: Any) -> str:
    """将原始结果包装为 {code, message, data} 文本。"""
    code = 0
    message = "success"
    if isinstance(data, dict):
        result_type = data.get("result_type", "normal")
        if result_type in ("rejected", "ask_user"):
            code = 500
            message = data.get("overflow_notice") or str(result_type)

    return dump_json({"code": code, "message": message, "data": data})


def _resolve_tool_input_schema(tool_name: str, loader: Any) -> dict[str, Any]:
    """Resolve the tool input schema for validation."""
    scope = _find_action_scope(loader, tool_name)
    if scope is None:
        return {"type": "object", "properties": {}}

    scope_type, scope_code = scope
    if scope_type == "view":
        view = loader.get_view(scope_code)
        schema = view.get_action_schema(tool_name)
    else:
        obj = loader.get_object(scope_code)
        schema = obj.get_action_schema(tool_name)

    input_schema = schema.get("inputSchema")
    if isinstance(input_schema, dict):
        return input_schema
    return {"type": "object", "properties": {}}


def _validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    loader: Any,
) -> list[TextContent] | None:
    """Validate tool arguments against the resolved input schema."""
    schema = _resolve_tool_input_schema(tool_name, loader)
    errors: list[str] = []

    def _validate_value(value: Any, node: dict[str, Any], path: str) -> None:
        expected_type = node.get("type")
        if "enum" in node:
            enum_values = list(node.get("enum") or [])
            if value not in enum_values:
                errors.append(f"{value!r} is not one of {enum_values}")
                return
        if expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path or 'value'} must be an object")
                return
            properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            required = node.get("required") if isinstance(node.get("required"), list) else []
            for required_name in required:
                if required_name not in value:
                    errors.append(f"{required_name} is required")
            for key, child in properties.items():
                if key in value and isinstance(child, dict):
                    child_path = f"{path}.{key}" if path else key
                    _validate_value(value[key], child, child_path)
        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"{path or 'value'} must be an array")
                return
            items_schema = node.get("items")
            if isinstance(items_schema, dict):
                for index, item in enumerate(value):
                    _validate_value(item, items_schema, f"{path}[{index}]")
        elif expected_type == "string" and not isinstance(value, str):
            errors.append(f"{path or 'value'} must be a string")
        elif expected_type == "integer" and not isinstance(value, int):
            errors.append(f"{path or 'value'} must be an integer")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"{path or 'value'} must be a number")
        elif expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"{path or 'value'} must be a boolean")

    _validate_value(arguments, schema, "")
    if not errors:
        return None
    logger.exception(
        "call_tool input validation failed: tool=%s arguments=%s",
        tool_name,
        json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
    )
    return [
        TextContent(
            type="text", text=format_input_validation_error(get_current_language(), errors[0])
        )
    ]


def _wrap_raw_data_as_payload(data: Any) -> dict[str, Any]:
    """将原始 data 结果包装成与 SDK 一致的 MCP payload。"""
    return {
        "content": [{"type": "text", "text": _build_sdk_envelope_text(data)}],
        "isError": False,
    }


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
                            {"error": format_loader_not_initialized(get_current_language())},
                            ensure_ascii=False,
                        ),
                    )
                ]
            loader = snapshot.loader
            from datacloud_data_sdk.context import get_current_context, get_tool_call_detail

            include_tool_call_detail = get_tool_call_detail()
            if include_tool_call_detail:
                current_ctx = get_current_context()
                current_ctx.gateway_context = _McpGatewayContext(
                    server.request_context.session,
                    str(server.request_context.request_id),
                )

            if name == "unified_data_query":
                from datacloud_data_service.tools.unified_query import UnifiedQuery

                query = UnifiedQuery(loader)
                result = await query.execute(
                    question=tool_arguments.get("question", ""),
                    view_id=tool_arguments.get("view_id", ""),
                    object_ids=tool_arguments.get("object_ids"),
                    knowledge_context=tool_arguments.get("knowledge_context"),
                    include_plan=include_tool_call_detail,
                )
                text = _render_tool_call_text(result, include_detail=include_tool_call_detail)
                return [TextContent(type="text", text=text)]

            scope = _find_action_scope(loader, name, snapshot=snapshot)
            if scope is None:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": format_unknown_tool(get_current_language(), name)},
                            ensure_ascii=False,
                        ),
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
                            type="text",
                            text=json.dumps(
                                {"error": translate_exception(exc, get_current_language())},
                                ensure_ascii=False,
                            ),
                        )
                    ]
                payload = _wrap_raw_data_as_payload(raw)
                text = _render_tool_call_text(payload, include_detail=include_tool_call_detail)
                return [TextContent(type="text", text=text)]
            else:
                # 对象级动作：走原有 ActionExecutor
                from datacloud_data_service.tools.action_executor import ActionExecutor

                executor = ActionExecutor(loader)
                result = await executor.execute(scope_code, name, tool_arguments)
                text = _render_tool_call_text(result, include_detail=include_tool_call_detail)
                return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.exception("call_tool failed: %s", e)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": translate_exception(e, get_current_language())},
                        ensure_ascii=False,
                    ),
                )
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
            "tool_call_detail": _parse_bool_header(headers.get(_TOOL_CALL_DETAIL_HEADER)),
            "language": headers.get("x-language", headers.get("accept-language", "")),
        }
        try:
            with InvocationContext(**ctx_kwargs):
                await session_manager.handle_request(scope, logging_receive, send)
        except Exception as e:
            logger.exception("MCP request failed: %s", e)
            from starlette.responses import JSONResponse

            resp = JSONResponse(
                {"error": translate_exception(e, get_current_language())},
                status_code=500,
            )
            await resp(scope, receive, send)

    return handle_streamable_http
