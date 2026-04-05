"""
OQL 工具模块

提供 QueryObjects 和 ExecuteAction 两个工具，用于 LLM 调用本体查询和动作执行。
"""

from datacloud_analysis.tools.oql.query_objects import query_objects
from datacloud_analysis.tools.oql.execute_action import execute_action

__all__ = [
    "query_objects",
    "execute_action",
]
