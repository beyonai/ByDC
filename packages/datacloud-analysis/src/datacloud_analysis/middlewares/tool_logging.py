"""工具调用日志中间件 - 推送工具调用过程到前端"""

from __future__ import annotations
from typing import Any, Callable, Awaitable
import logging

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.prebuilt.tool_node import ToolCallRequest

logger = logging.getLogger(__name__)


class ToolCallLoggingMiddleware(AgentMiddleware):
    """
    工具调用日志中间件

    推送工具调用过程到前端，包括：
    - 工具名称
    - 入参（tool_call["args"]）
    - 出参（工具返回值）

    创建层级结构（与老版本一致）：
    - 层级1：工具名称（使用 sub_step）
    - 层级2：入参详情
    - 层级3：出参详情
    """

    tools: list = []

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """在工具调用前后推送消息到前端。"""
        logger.info("ToolCallLoggingMiddleware.awrap_tool_call: START")

        # 获取 gateway_context
        gateway_context = self._get_gateway_context(request)
        logger.info(
            "ToolCallLoggingMiddleware: gateway_context=%s",
            "present" if gateway_context else "None",
        )

        if gateway_context is None:
            # 没有 gateway_context，直接执行工具
            logger.warning("ToolCallLoggingMiddleware: no gateway_context, skipping logging")
            return await handler(request)

        # 提取工具信息
        tool_name = request.tool_call.get("name", "unknown_tool")
        tool_args = request.tool_call.get("args", {})
        logger.info(
            "ToolCallLoggingMiddleware: tool_name=%s args_keys=%s",
            tool_name,
            list(tool_args.keys()) if tool_args else [],
        )
        logger.info("ToolCallLoggingMiddleware: tool_args=%s", tool_args)

        # 检查是否是 AGENT 类型工具
        is_agent_delegate = self._is_agent_delegate_tool(request)
        logger.info("ToolCallLoggingMiddleware: is_agent_delegate=%s", is_agent_delegate)

        try:
            # 层级1：创建工具调用节点
            async with gateway_context.sub_step(tool_name):
                # 层级2：推送入参
                await self._emit_child_think(
                    gateway_context, f"调用参数：{self._format_args(tool_args)}"
                )

                if is_agent_delegate:
                    # AGENT 类型工具：使用 delegate_parent_scope
                    result = await self._handle_agent_delegate(
                        gateway_context,
                        request,
                        handler,
                    )
                else:
                    # 普通工具：直接执行
                    result = await handler(request)

                # 层级3：推送出参
                await self._emit_child_think(
                    gateway_context, f"返回结果：{self._format_result(result)}"
                )

                logger.info("ToolCallLoggingMiddleware: tool_result=%s", result)

                return result

        except Exception as exc:
            # 推送错误信息
            await self._emit_child_think(gateway_context, f"执行失败：{str(exc)}")
            raise

    def _is_agent_delegate_tool(self, request: ToolCallRequest) -> bool:
        """检查工具是否是 AGENT 类型（agent_delegate）。"""
        try:
            tool = request.tool
            is_delegate_flag = getattr(tool, "_is_agent_delegate", False)
            return isinstance(is_delegate_flag, bool) and is_delegate_flag
        except Exception:
            return False

    async def _handle_agent_delegate(
        self,
        gateway_context: Any,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """处理 AGENT 类型工具调用（子 Agent 异步调用）。

        使用 delegate_parent_scope 创建代理作用域，确保子 Agent 的流式输出
        能够正确挂载到父 Agent 的消息层级下。
        """
        from contextlib import nullcontext

        # 获取代理作用域工厂
        delegate_parent_scope_factory = getattr(
            gateway_context,
            "delegate_parent_scope",
            None,
        )
        delegate_parent_scope = nullcontext()

        if callable(delegate_parent_scope_factory):
            # 创建代理作用域，传入当前 message_id
            current_message_id = str(getattr(gateway_context, "message_id", "") or "")
            delegate_parent_scope = delegate_parent_scope_factory(current_message_id)

        # 在代理作用域内执行工具
        with delegate_parent_scope:
            # 调用工具（内部会触发 interrupt，等待子 Agent 完成）
            result = await handler(request)

        return result

    def _get_gateway_context(self, request: ToolCallRequest) -> Any | None:
        """从 request 中获取 gateway_context。"""
        try:
            # ToolCallRequest.runtime 是 ToolRuntime，包含 config 属性
            return request.runtime.config.get("configurable", {}).get("gateway_context")
        except Exception:
            return None

    async def _emit_child_think(
        self,
        gateway_context: Any,
        text: str,
    ) -> None:
        """推送子节点思考内容（与老版本实现一致）。"""
        try:
            from datacloud_data_sdk.stream_text import coerce_stream_chunk_text
            from by_framework import StreamChunkEvent

            # 生成子节点 message_id
            child_message_id = self._new_message_id(gateway_context)
            parent_message_id = str(getattr(gateway_context, "message_id", "") or "")

            # 创建消息块
            chunk = StreamChunkEvent(content=coerce_stream_chunk_text(text))

            # 推送参数
            emit_kwargs = {
                "event_type": "1001",  # 思考过程事件类型
                "content_type": "1002",  # 思考内容类型
            }
            if child_message_id:
                emit_kwargs["message_id"] = child_message_id
            if parent_message_id:
                emit_kwargs["parent_message_id"] = parent_message_id

            await gateway_context.emit_chunk(chunk, **emit_kwargs)

        except Exception as exc:
            logger.debug("_emit_child_think failed: %s", exc)

    def _new_message_id(self, gateway_context: Any) -> str:
        """生成新的 message_id（与老版本实现一致）。"""
        generate_message_id = getattr(gateway_context, "generate_message_id", None)
        if callable(generate_message_id):
            try:
                return str(generate_message_id() or "")
            except Exception:
                return ""
        return ""

    def _format_args(self, args: dict[str, Any]) -> str:
        """格式化入参为可读字符串。"""
        if not args:
            return "{}"

        # 简化展示，避免过长
        import json

        try:
            formatted = json.dumps(args, ensure_ascii=False, indent=2)
            # 限制长度
            if len(formatted) > 500:
                return formatted[:500] + "\n... (已截断)"
            return formatted
        except Exception:
            return str(args)

    def _format_result(self, result: Any) -> str:
        """格式化返回结果为可读字符串。"""
        # 如果是字典且包含 status 字段，提取关键信息
        if isinstance(result, dict):
            status = result.get("status")
            if status:
                record_count = 0
                if isinstance(result.get("result"), dict):
                    records = result["result"].get("records", [])
                    if isinstance(records, list):
                        record_count = len(records)

                return f"状态: {status}, 记录数: {record_count}"

        # 通用格式化
        import json

        try:
            formatted = json.dumps(result, ensure_ascii=False, indent=2)
            if len(formatted) > 500:
                return formatted[:500] + "\n... (已截断)"
            return formatted
        except Exception:
            return str(result)[:500]
