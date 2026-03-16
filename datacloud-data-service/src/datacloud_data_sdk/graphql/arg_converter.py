"""GraphQL 参数到执行层参数的转换。"""

from typing import Any

# GraphQL where 中的操作符 -> filters 中的 op
# 有 value 的操作符
_OPS_WITH_VALUE = frozenset({"eq", "neq", "in", "gt", "gte", "lt", "lte", "like"})
# 无 value 的操作符
_OPS_WITHOUT_VALUE = frozenset({"is_null", "is_not_null"})


def where_to_filters(where: dict[str, Any] | None) -> dict[str, Any]:
    """将 GraphQL where 格式转换为 filters 格式。

    GraphQL where 格式: { field: { eq: "x" } } 或 { field: { gte: 100 } }
    目标 filters 格式: { field: { op: "eq", value: "x" } }

    支持: eq, neq, in, gt, gte, lt, lte, like, is_null, is_not_null
    is_null / is_not_null 无 value，格式为 { op: "is_null" } 或 { op: "is_not_null" }

    空 where 或 None 返回 {}。
    """
    if where is None or not where:
        return {}

    result: dict[str, Any] = {}
    for field, cond in where.items():
        if not isinstance(cond, dict):
            continue
        for op_key, op_value in cond.items():
            if op_key in _OPS_WITH_VALUE:
                result[field] = {"op": op_key, "value": op_value}
                break
            if op_key in _OPS_WITHOUT_VALUE and op_value:
                result[field] = {"op": op_key}
                break
    return result
