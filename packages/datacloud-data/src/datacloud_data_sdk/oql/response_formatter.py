"""
OQL 响应格式转换工具

提供格式转换函数，将 OqlRouter.route() 返回的内部格式转换为标准响应格式。
供调用方（如 datacloud-analysis）使用。
"""

from __future__ import annotations
from typing import Any
from datacloud_data_sdk.oql.models import OQLError


def format_oql_response(
    tool: str, records: list[dict], total: int, limit: int, offset: int = 0
) -> dict[str, Any]:
    """
    将 OqlRouter.route() 返回的 list[dict] 转换为标准响应格式。

    符合《本体推理引擎重构方案.md》§2.2.8 定义的标准响应格式。

    Args:
        tool: 工具名称（"QueryObjects" 或 "ExecuteAction"）
        records: OqlRouter.route() 返回的记录列表，每条记录是 {字段名: 值} 字典
        total: 总记录数（需要调用方通过 COUNT 查询或 API 元数据获取）
        limit: 分页大小
        offset: 分页偏移量

    Returns:
        标准响应字典，格式为:
        {
            "status": "success",
            "tool": str,
            "result": {
                "columns": list[str],
                "rows": list[list[Any]],
                "total": int,
                "returned": int,
                "pagination": {
                    "limit": int,
                    "offset": int,
                    "has_next": bool
                }
            }
        }

    Example:
        >>> records = [{"name": "张三", "age": 30}, {"name": "李四", "age": 25}]
        >>> response = format_oql_response("QueryObjects", records, 100, 20, 0)
        >>> response["result"]["columns"]
        ["name", "age"]
        >>> response["result"]["rows"]
        [["张三", 30], ["李四", 25]]
    """
    if not records:
        return {
            "status": "success",
            "tool": tool,
            "result": {
                "columns": [],
                "rows": [],
                "total": total,
                "returned": 0,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_next": False,
                },
            },
        }

    # 提取列名（使用第一条记录的键）
    columns = list(records[0].keys())

    # 转换为行数组格式
    rows = [[row.get(col) for col in columns] for row in records]

    return {
        "status": "success",
        "tool": tool,
        "result": {
            "columns": columns,
            "rows": rows,
            "total": total,
            "returned": len(rows),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_next": total > (offset + limit),
            },
        },
    }


def format_oql_error(error: OQLError) -> dict[str, Any]:
    """
    将 OQLError 异常转换为标准错误响应格式。

    符合《本体推理引擎重构方案.md》§2.2.8 定义的错误响应格式。

    Args:
        error: OQLError 异常对象

    Returns:
        标准错误响应字典，格式为:
        {
            "status": "error",
            "error_code": str,
            "message": str,
            "detail": dict
        }

    Example:
        >>> from datacloud_data_sdk.oql.models import OQLError, OQLErrorCode
        >>> error = OQLError(
        ...     OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
        ...     "对象 'Employee' 不存在",
        ...     {"object_type": "Employee"}
        ... )
        >>> response = format_oql_error(error)
        >>> response["status"]
        "error"
        >>> response["error_code"]
        "OQL_ERR_UNKNOWN_OBJECT"
    """
    return {
        "status": "error",
        "error_code": error.code,
        "message": error.message,
        "detail": error.details,
    }
