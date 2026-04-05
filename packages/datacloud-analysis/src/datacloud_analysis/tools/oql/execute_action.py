"""
ExecuteAction 工具实现

提供本体动作执行功能，支持：
- 创建对象
- 更新对象
- 删除对象
- 自定义业务动作
"""

from __future__ import annotations
from typing import Any, Optional
from langchain_core.tools import tool

from datacloud_data_sdk.oql import format_oql_error, OQLError
from datacloud_analysis.dependencies import get_action_service


@tool
def execute_action(
    action_type: str,
    target_objects: Optional[list[str]] = None,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    执行有副作用的业务动作。

    支持的动作类型：
    1. 标准CRUD动作：create, update, delete
    2. 自定义业务动作：由本体定义的特定业务操作

    Args:
        action_type: 动作类型名称（必须来自本体注册表的动作定义）
        target_objects: 目标对象ID列表（对于update/delete动作必填）
        payload: 动作参数字典，具体字段由动作类型决定

    Returns:
        标准响应字典:
        {
            "status": "success" | "error",
            "tool": "ExecuteAction",
            "result": {
                "action_type": str,
                "affected_count": int,
                "affected_objects": list[str],
                "details": dict
            }
        }

    Examples:
        >>> # 创建对象
        >>> execute_action(
        ...     action_type="创建员工",
        ...     payload={
        ...         "姓名": "张三",
        ...         "部门": "技术部",
        ...         "职位": "工程师",
        ...         "入职日期": "2024-01-01"
        ...     }
        ... )

        >>> # 更新对象
        >>> execute_action(
        ...     action_type="更新员工信息",
        ...     target_objects=["EMP001", "EMP002"],
        ...     payload={
        ...         "部门": "产品部",
        ...         "更新原因": "组织调整"
        ...     }
        ... )

        >>> # 删除对象
        >>> execute_action(
        ...     action_type="删除员工",
        ...     target_objects=["EMP003"]
        ... )

        >>> # 自定义业务动作
        >>> execute_action(
        ...     action_type="发送延误通知",
        ...     target_objects=["FL001", "FL002"],
        ...     payload={
        ...         "通知类型": "短信",
        ...         "模板": "延误致歉"
        ...     }
        ... )
    """
    try:
        # 构建 Action 参数
        action_params = {
            "action_type": action_type,
        }

        if target_objects is not None:
            action_params["target_objects"] = target_objects
        if payload is not None:
            action_params["payload"] = payload

        # 获取依赖
        action_service = get_action_service()

        # 调用 Action Service
        result = action_service.execute(action_params)

        # 返回标准响应
        return {
            "status": "success",
            "tool": "ExecuteAction",
            "result": {
                "action_type": action_type,
                "affected_count": result.get("affected_count", 0),
                "affected_objects": result.get("affected_objects", []),
                "details": result.get("details", {}),
            },
        }

    except OQLError as e:
        return format_oql_error(e)
    except Exception as e:
        # 未预期的异常
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"动作执行失败: {str(e)}",
            "detail": {"exception_type": type(e).__name__},
        }
