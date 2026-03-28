"""
统一数据查询工具模块

本模块提供统一的数据查询接口，封装了 View 和 Object 的查询能力。
SDK 层已负责结果格式化（{code, message, data}）与溢出处理，
本模块只负责选择查询入口并将结果封装为 MCP 格式返回。

使用示例：
    query = UnifiedQuery(loader)
    result = await query.execute(
        question="查询所有活跃用户",
        view_id="user_view"
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.result_formatter import build_error_data

logger = logging.getLogger(__name__)


class UnifiedQuery:
    """
    统一数据查询工具

    封装 View.query() 和 Object.query()，提供统一的查询入口。
    SDK 返回的 {code, message, data} 结果直接透传给调用方。

    Attributes:
        _loader: 本体加载器实例

    Example:
        query = UnifiedQuery(loader)
        result = await query.execute("查询销售额", view_id="sales_view")
    """

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    async def execute(
        self,
        question: str,
        view_id: str = "",
        object_ids: list[str] | None = None,
        include_plan: bool = True,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """
        执行自然语言查询

        根据参数选择查询方式：
        1. 指定 view_id：使用预定义视图查询
        2. 指定单个 object_id：使用对象查询
        3. 多个或全部对象：自动构建视图查询

        返回 MCP 格式，content[0].text 内嵌 SDK 的 {code, message, data} JSON。

        Args:
            question: 自然语言问题
            view_id: 视图 ID（可选）
            object_ids: 对象 ID 列表（可选）
            include_plan: 是否在结果中包含执行计划
            page: 页码（保留，暂未使用）
            page_size: 每页大小（保留，暂未使用）

        Returns:
            dict: MCP 格式的查询结果
        """
        def _wrap(data: dict[str, Any]) -> dict[str, Any]:
            result_type = data.get("result_type", "normal")
            if result_type in ("rejected", "ask_user"):
                code = 500
                message = data.get("overflow_notice") or result_type
            else:
                code = 0
                message = "success"
            payload = {"code": code, "message": message, "data": data}
            return {
                "content": [
                    {"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }

        def _wrap_error(msg: str, result_type: str, trace: dict[str, Any]) -> dict[str, Any]:
            return _wrap(build_error_data(msg, result_type=result_type, trace=trace))

        try:
            if view_id:
                view = self._loader.get_view(view_id)
                result = await view.query(question, include_plan=include_plan)
            elif object_ids and len(object_ids) == 1:
                obj = self._loader.get_object(object_ids[0])
                result = await obj.query(question, include_plan=include_plan)
            else:
                all_ids = object_ids or [c.object_code for c in self._loader.get_ontology_classes()]
                from datacloud_data_sdk.view import View
                from datacloud_data_sdk.relation import Relation

                objects = [self._loader.get_object(oid) for oid in all_ids]
                object_set = set(all_ids)
                relations = [
                    Relation(
                        from_object=r.source_class,
                        to_object=r.target_class,
                        cardinality=r.relation_type,
                        join_keys=r.join_keys,
                        description=r.description,
                    )
                    for r in self._loader.get_ontology_relations()
                    if r.source_class in object_set and r.target_class in object_set
                ]
                view = View(
                    view_id="auto_view",
                    view_name="自动视图",
                    description="",
                    objects=objects,
                    relations=relations,
                )
                result = await view.query(question, include_plan=include_plan)

            return _wrap(result)

        except Exception as e:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(e)
            return _wrap_error(str(e), "rejected", {"question": question, "view_id": view_id})
