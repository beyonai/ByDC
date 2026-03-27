"""
动作执行器模块

本模块提供操作类工具的执行流水线，处理动作调用和结果格式化。
SDK 层（Action.execute）已负责结果格式化（{code, message, data}）与溢出处理，
本模块只负责调用对象动作并将结果封装为 MCP 格式返回。

使用示例：
    executor = ActionExecutor(loader)
    result = await executor.execute(
        object_code="user",
        action_code="create_user",
        arguments={"name": "张三"}
    )
"""

from __future__ import annotations

import json
from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader


class ActionExecutor:
    """
    操作类工具执行流水线

    参数映射、术语解析、结果格式化与溢出处理均在 SDK Action.execute 内自闭环；
    ActionExecutor 仅透传 arguments、调用 invoke_action、封装 MCP 返回。

    Attributes:
        _loader: 本体加载器实例

    Example:
        executor = ActionExecutor(loader)
        result = await executor.execute("order", "cancel_order", {"order_id": "123"})
    """

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    async def execute(
        self,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行操作类动作

        执行流程：
        1. 验证动作存在
        2. 调用对象动作执行（SDK 内部完成格式化与溢出处理）
        3. 封装为 MCP 返回格式

        Args:
            object_code: 对象代码
            action_code: 动作代码
            arguments: 动作参数

        Returns:
            dict: MCP 格式的执行结果，content[0].text 内嵌 {code, message, data} JSON

        Raises:
            ActionNotFoundError: 动作不存在时抛出
        """
        cls = self._loader.get_ontology_class(object_code)
        for a in cls.actions:
            if a.action_code == action_code:
                break
        else:
            from datacloud_data_sdk.exceptions import ActionNotFoundError

            raise ActionNotFoundError(object_code, action_code)

        obj = self._loader.get_object(object_code)
        try:
            result = await obj.invoke_action(action_code, arguments)
        except Exception as exc:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(exc)
            error_payload = {
                "code": 500,
                "message": str(exc),
                "data": {"result_type": "rejected", "overflow_notice": str(exc)},
            }
            return {
                "content": [
                    {"type": "text", "text": json.dumps(error_payload, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }

        result_type = result.get("result_type", "normal")
        if result_type in ("rejected", "ask_user"):
            code = 500
            message = result.get("overflow_notice") or result_type
        else:
            code = 0
            message = "success"

        payload = {"code": code, "message": message, "data": result}
        return {
            "content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}
            ],
            "isError": False,
        }
