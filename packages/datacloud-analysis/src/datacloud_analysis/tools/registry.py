"""工具注册模块。

向 Deep Agents create_deep_agent(tools=[...]) 提供 OQL 工具列表。

注意：
- emit_result 由 DatacloudOutputMiddleware.tools 动态注入，不在此注册（Decision 8）
- ask_user / code_exec / file_io / sandbox 已由 SDK 内置替代，不在此注册
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register_oql_tools() -> list[Any]:
    """注册 OQL 核心工具：query_objects + execute_action。

    Returns:
        [query_objects, execute_action]
    """
    from datacloud_analysis.tools.oql import execute_action, query_objects  # noqa: PLC0415

    tools = [query_objects, execute_action]
    logger.info("Registered OQL tools: %s", [t.name for t in tools])
    return tools


def register_all_tools() -> list[Any]:
    """注册主 Agent 的全部静态工具。

    返回的列表传入 create_deep_agent(tools=[...])。
    SDK 内置工具（ls/read_file/write_file/execute/task 等）由中间件自动提供，无需此处声明。

    Returns:
        OQL 工具列表
    """
    tools = register_oql_tools()
    logger.info("Total registered tools: %d names=%s", len(tools), [t.name for t in tools])
    return tools


def get_tool_by_name(name: str) -> Any:
    """根据名称获取工具（用于测试/调试）。

    Args:
        name: 工具名称

    Returns:
        工具实例

    Raises:
        ValueError: 工具不存在
    """
    all_tools = register_all_tools()
    for t in all_tools:
        if t.name == name:
            return t
    raise ValueError(f"Tool '{name}' not found in registered tools")
