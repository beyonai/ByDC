"""MCP客户端 - 基于 langchain-mcp-adapters 官方实现。

使用 langchain-mcp-adapters 的 StreamableHttpConnection + load_mcp_tools，
通过标准 MCP Streamable HTTP 协议（JSON-RPC 2.0）与服务端通信。

服务端挂载点：POST /api/v1/mcp（datacloud-data 的 routes.py:286）
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _run_async(coro: Any, timeout: float = 60.0) -> Any:
    """在独立线程的新事件循环中运行异步协程。

    使用独立线程是为了避免与调用方（byclaw-data worker / LangGraph）
    已有的事件循环发生冲突。
    loop.shutdown_asyncgens() 确保 SSE 响应流等 async generator 被正确关闭，
    消除 "Task was destroyed but it is pending" 警告。
    """
    result_holder: list[Any] = []
    exc_holder: list[BaseException] = []

    def _target() -> None:
        loop = asyncio.new_event_loop()
        try:
            result_holder.append(loop.run_until_complete(coro))
        except Exception as e:
            exc_holder.append(e)
        finally:
            # 关闭所有挂起的 async generator（修复 aiter_bytes 未 aclose 警告）
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if exc_holder:
        raise exc_holder[0]
    if not result_holder:
        raise TimeoutError(f"MCP 请求超时（>{timeout}s）")
    return result_holder[0]


def _build_connection(endpoint: str, mounted_objects: list[str]) -> dict[str, Any]:
    """构建 StreamableHttpConnection 配置字典。

    URL 末尾保留斜杠，避免 Starlette mount 触发 307 重定向。
    """
    conn: dict[str, Any] = {
        "transport": "streamable_http",
        # 确保末尾有 /，Starlette mount 的路径以 / 结尾才不会 307
        "url": endpoint if endpoint.endswith("/") else endpoint + "/",
    }
    if mounted_objects:
        conn["headers"] = {
            "x-object-ids": ",".join(mounted_objects),
            "x-tool-list-mode": "per_object",
        }
    return conn


class MCPClient:
    """同步 MCP 客户端封装。

    供 byclaw-data worker.py 在计算 cache hash 时调用：
    仅需 list_tools() 获取工具名列表，不需要实际调用工具。
    """

    def __init__(self, endpoint: str, mounted_objects: list[str] | None = None):
        """
        Args:
            endpoint: MCP 挂载点，如 http://host:8080/api/v1/mcp
            mounted_objects: 挂载的对象 ID 列表
        """
        self.endpoint = endpoint
        self.mounted_objects = mounted_objects or []

    def list_tools(self) -> list[dict[str, Any]]:
        """获取工具列表，返回 [{"name": ..., "description": ...}] 格式。

        供 worker.py cache hash 计算使用。
        """
        try:
            lc_tools: list[BaseTool] = _run_async(self._alist_tools())
            result = [{"name": t.name, "description": t.description} for t in lc_tools]
            logger.info("MCPClient.list_tools: received %d tools", len(result))
            return result
        except Exception as e:
            logger.error("MCPClient.list_tools: failed to list tools: %s", e)
            return []

    async def _alist_tools(self) -> list[BaseTool]:
        from langchain_mcp_adapters.tools import load_mcp_tools

        conn = _build_connection(self.endpoint, self.mounted_objects)
        return await load_mcp_tools(session=None, connection=conn)

    def close(self) -> None:
        """无需显式关闭（每次调用均为短连接）。"""


def create_mcp_tools(
    mcp_endpoint: str,
    mounted_objects: list[str] | None = None,
) -> list[BaseTool]:
    """从 MCP 服务创建 LangChain 工具列表。

    返回的工具是自包含的（connection-based）：每次 invoke 自动建立
    独立 MCP 会话，执行完后关闭，无需外部管理生命周期。

    Args:
        mcp_endpoint: MCP 端点，如 http://host:8080/api/v1/mcp
        mounted_objects: 挂载的对象 ID 列表

    Returns:
        LangChain BaseTool 列表，可直接绑定到 LangGraph 节点
    """
    endpoint = mcp_endpoint
    objects = mounted_objects or []
    logger.info("create_mcp_tools: endpoint=%s objects=%s", endpoint, objects)

    try:
        tools: list[BaseTool] = _run_async(_async_create_mcp_tools(endpoint, objects))
        logger.info("create_mcp_tools: created %d tools", len(tools))
        return tools
    except Exception as e:
        logger.error("create_mcp_tools: failed: %s", e)
        return []


async def _async_create_mcp_tools(
    endpoint: str,
    mounted_objects: list[str],
) -> list[BaseTool]:
    from langchain_mcp_adapters.tools import load_mcp_tools

    conn = _build_connection(endpoint, mounted_objects)
    return await load_mcp_tools(session=None, connection=conn)
