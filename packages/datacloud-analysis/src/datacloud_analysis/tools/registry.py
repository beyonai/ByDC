"""
工具注册模块

负责注册所有可用工具到 Agent，包括：
- OQL 工具（QueryObjects, ExecuteAction）
- 现有工具（ask_user, code_exec, file_io）
"""

from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)


def register_oql_tools() -> list[Any]:
    """
    注册 OQL 工具。

    Returns:
        OQL 工具列表 [query_objects, execute_action]
    """
    from datacloud_analysis.tools.oql import query_objects, execute_action

    tools = [query_objects, execute_action]
    logger.info("Registered OQL tools: %s", [t.name for t in tools])
    return tools


def register_core_tools() -> list[Any]:
    """
    注册核心工具。

    Returns:
        核心工具列表 [ask_user, execute_code, file_io]
    """
    from datacloud_analysis.tools.ask_user import ask_user
    from datacloud_analysis.tools.code_exec import execute_code
    from datacloud_analysis.tools.file_io import read_file, write_file

    tools = [
        ask_user,
        execute_code,
        read_file,
        write_file,
    ]
    logger.info("Registered core tools: %s", [t.name for t in tools])
    return tools


def register_all_tools() -> list[Any]:
    """
    注册所有工具。

    Returns:
        所有工具列表
    """
    tools = []
    tools.extend(register_oql_tools())
    tools.extend(register_core_tools())

    logger.info("Total registered tools: %d", len(tools))
    return tools


def get_tool_by_name(name: str) -> Any:
    """
    根据名称获取工具。

    Args:
        name: 工具名称

    Returns:
        工具实例

    Raises:
        ValueError: 工具不存在
    """
    all_tools = register_all_tools()
    for tool in all_tools:
        if tool.name == name:
            return tool

    raise ValueError(f"Tool '{name}' not found")
