"""
QueryObjects 工具实现

提供本体对象查询功能，支持：
- 列表查询
- 详情查询
- 聚合统计
- 关系漫游
"""

from __future__ import annotations
from typing import Any, Optional
from langchain_core.tools import tool

from datacloud_data_sdk.oql import OqlRouter, format_oql_response, format_oql_error, OQLError
from datacloud_analysis.dependencies import (
    get_oql_router,
    get_term_resolver,
    get_executor,
    get_datasource_registry,
)


@tool
def query_objects(
    object_type: str,
    select: Optional[list[str]] = None,
    where: Optional[list[dict[str, Any]]] = None,
    include_links: Optional[list[dict[str, Any]]] = None,
    metrics: Optional[list[dict[str, Any]]] = None,
    group_by: Optional[list[dict[str, Any]]] = None,
    having: Optional[list[dict[str, Any]]] = None,
    order_by: Optional[list[dict[str, str]]] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    查询本体对象或视图的实例列表、详情、聚合统计。

    支持的查询模式：
    1. 列表查询：返回对象实例列表
    2. 详情查询：通过 where 条件查询单个对象详情
    3. 聚合查询：使用 metrics + group_by 进行统计分析
    4. 关系漫游：通过 include_links 获取关联对象数据

    Args:
        object_type: 对象类型名或视图名（必须来自本体注册表）
        select: 返回属性列表，省略则返回全部非计算属性
        where: 行级过滤条件数组，支持 eq/ne/gt/gte/lt/lte/in/nin/like/between/isNull/relativeDate
        include_links: 关系漫游数组（仅DB主对象支持，聚合模式禁用）
        metrics: 聚合指标数组，每项包含 field 和 aggregation (count/sum/avg/max/min/count_distinct)
        group_by: 分组字段数组，每项包含 field 和可选的 time_bucket
        having: 聚合后过滤条件（仅聚合模式支持）
        order_by: 排序规则数组，每项包含 field 和 direction (asc/desc)
        limit: 返回记录数上限（默认100，最大1000）
        offset: 分页偏移量（默认0）

    Returns:
        标准响应字典:
        {
            "status": "success" | "error",
            "tool": "QueryObjects",
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

    Examples:
        >>> # 列表查询
        >>> query_objects(
        ...     object_type="员工",
        ...     select=["姓名", "部门", "薪资"],
        ...     where=[{"field": "部门", "op": "eq", "value": "技术部"}],
        ...     order_by=[{"field": "薪资", "direction": "desc"}],
        ...     limit=20
        ... )

        >>> # 聚合查询
        >>> query_objects(
        ...     object_type="订单",
        ...     metrics=[
        ...         {"field": "订单金额", "aggregation": "sum", "alias": "总金额"},
        ...         {"field": "订单ID", "aggregation": "count", "alias": "订单数"}
        ...     ],
        ...     group_by=[{"field": "客户ID"}],
        ...     having=[{"field": "总金额", "op": "gt", "value": 10000}]
        ... )

        >>> # 关系漫游
        >>> query_objects(
        ...     object_type="订单",
        ...     select=["订单号", "金额"],
        ...     include_links=[
        ...         {"relation": "订单_客户", "fields": ["客户名称", "联系电话"]},
        ...         {"relation": "订单_产品", "fields": ["产品名称", "单价"]}
        ...     ]
        ... )
    """
    try:
        # 构建 OQL 参数
        oql_params = {
            "object": object_type,
            "limit": limit,
            "offset": offset,
        }

        if select is not None:
            oql_params["fields"] = select
        if where is not None:
            oql_params["where"] = where
        if include_links is not None:
            oql_params["include_links"] = include_links
        if metrics is not None:
            oql_params["metrics"] = metrics
        if group_by is not None:
            oql_params["group_by"] = group_by
        if having is not None:
            oql_params["having"] = having
        if order_by is not None:
            oql_params["order_by"] = order_by

        # 获取依赖
        router = get_oql_router()
        term_resolver = get_term_resolver()
        executor = get_executor()
        datasource_registry = get_datasource_registry()

        # 调用 OqlRouter
        records = router.route(
            oql_params=oql_params,
            term_resolver=term_resolver,
            executor=executor,
            datasource_registry=datasource_registry,
        )

        # 格式化响应
        # TODO: total 需要通过 COUNT 查询获取，这里暂时使用 len(records)
        # 在实际使用中，如果需要精确的 total，应该执行一次 COUNT 查询
        total = len(records)

        return format_oql_response(
            tool="QueryObjects",
            records=records,
            total=total,
            limit=limit,
            offset=offset,
        )

    except OQLError as e:
        return format_oql_error(e)
    except Exception as e:
        # 未预期的异常
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"查询执行失败: {str(e)}",
            "detail": {"exception_type": type(e).__name__},
        }
