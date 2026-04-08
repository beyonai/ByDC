"""MCP客户端 - 连接到datacloud-data的MCP服务。

通过HTTP SSE协议与MCP服务端通信，动态获取工具列表并执行工具调用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP客户端，用于与datacloud-data的MCP服务通信。"""

    def __init__(self, endpoint: str, mounted_objects: list[str] | None = None):
        """初始化MCP客户端。

        Args:
            endpoint: MCP服务端点，如 http://localhost:8080/api/v1/mcp/
            mounted_objects: 挂载的对象/视图列表
        """
        self.endpoint = endpoint.rstrip("/")
        self.mounted_objects = mounted_objects or []
        self.client = httpx.Client(timeout=30.0)

    def list_tools(self) -> list[dict[str, Any]]:
        """获取工具列表。

        Returns:
            工具定义列表
        """
        try:
            # 构建请求头
            headers = {
                "Content-Type": "application/json",
            }

            # 如果有挂载对象，添加到请求头
            if self.mounted_objects:
                headers["x-object-ids"] = ",".join(self.mounted_objects)
                headers["x-tool-list-mode"] = "unified"

            # 发送list_tools请求
            response = self.client.post(
                f"{self.endpoint}/list_tools",
                headers=headers,
                json={},
            )
            response.raise_for_status()

            result = response.json()
            tools = result.get("tools", [])
            logger.info("MCPClient.list_tools: received %d tools", len(tools))
            return tools

        except Exception as e:
            logger.error("MCPClient.list_tools: failed to list tools: %s", e)
            return []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用工具。

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        try:
            # 构建请求头
            headers = {
                "Content-Type": "application/json",
            }

            # 如果有挂载对象，添加到请求头
            if self.mounted_objects:
                headers["x-object-ids"] = ",".join(self.mounted_objects)

            # 发送call_tool请求
            response = self.client.post(
                f"{self.endpoint}/call_tool",
                headers=headers,
                json={
                    "name": name,
                    "arguments": arguments,
                },
            )
            response.raise_for_status()

            result = response.json()
            logger.info("MCPClient.call_tool: tool=%s status=%s", name, result.get("status"))
            return result

        except Exception as e:
            logger.error("MCPClient.call_tool: failed to call tool %s: %s", name, e)
            return {
                "status": "error",
                "error_code": "MCP_CALL_ERROR",
                "message": f"MCP工具调用失败: {e!s}",
            }

    def close(self):
        """关闭客户端连接。"""
        self.client.close()


def create_mcp_tools(
    mcp_endpoint: str,
    mounted_objects: list[str] | None = None,
) -> list[Any]:
    """从MCP服务创建工具列表。

    Args:
        mcp_endpoint: MCP服务端点
        mounted_objects: 挂载的对象/视图列表

    Returns:
        LangChain工具列表
    """
    logger.info("create_mcp_tools: endpoint=%s objects=%s", mcp_endpoint, mounted_objects)

    # 创建MCP客户端
    client = MCPClient(endpoint=mcp_endpoint, mounted_objects=mounted_objects)

    # 获取工具列表
    tool_defs = client.list_tools()

    if not tool_defs:
        logger.warning("create_mcp_tools: no tools returned from MCP service")
        return []

    # 为每个工具创建LangChain tool
    tools = []
    for tool_def in tool_defs:
        tool_name = tool_def.get("name", "")
        tool_description = tool_def.get("description", "")
        tool_schema = tool_def.get("inputSchema", {})

        if not tool_name:
            logger.warning("create_mcp_tools: skipping tool with no name")
            continue

        # 创建工具函数
        def make_tool_func(name: str):
            """创建工具函数闭包。"""
            def tool_func(**kwargs) -> Any:
                """MCP工具函数。"""
                return client.call_tool(name=name, arguments=kwargs)
            return tool_func

        # 使用@tool装饰器创建工具
        # 注意：这里简化处理，实际应该根据inputSchema动态生成参数
        mcp_tool = tool(
            name=tool_name,
            description=tool_description,
        )(make_tool_func(tool_name))

        tools.append(mcp_tool)
        logger.info("create_mcp_tools: created tool %s", tool_name)

    logger.info("create_mcp_tools: created %d tools", len(tools))
    return tools
