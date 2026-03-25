"""
动作执行器模块

本模块提供操作类工具的执行流水线，处理动作调用和结果格式化。

核心功能：
- 执行对象动作（API 调用或脚本执行）
- 查询类动作结果溢出处理
- MCP 格式结果封装

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

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_service.tools.query_result_overflow import apply_query_result_overflow


def _apply_overflow_if_query(result: dict[str, Any], loader: OntologyLoader) -> dict[str, Any]:
    """
    对查询类动作应用溢出处理
    
    当查询结果记录数超过阈值时，将数据存储为 CSV 文件。
    
    Args:
        result: 原始查询结果
        loader: 本体加载器实例
    
    Returns:
        dict: 处理后的结果
    """
    if "records" not in result or "meta" not in result:
        return result
    try:
        from datacloud_data_service.config import get_settings

        settings = get_settings()
        csv_manager = CsvStorageManager(settings.csv_base_dir)
        return apply_query_result_overflow(
            result,
            threshold=settings.query_result_csv_threshold,
            preview_rows=settings.query_result_preview_rows,
            csv_manager=csv_manager,
            api_base_url=settings.api_base_url,
        )
    except Exception:
        return result


class ActionExecutor:
    """
    操作类工具执行流水线
    
    参数映射、术语解析均在 SDK Action.execute 内自闭环；
    ActionExecutor 仅透传 arguments、调用 invoke_action、格式化 MCP 返回。
    
    Attributes:
        _loader: 本体加载器实例
    
    Example:
        executor = ActionExecutor(loader)
        result = await executor.execute("order", "cancel_order", {"order_id": "123"})
    """

    def __init__(self, loader: OntologyLoader) -> None:
        """
        初始化动作执行器
        
        Args:
            loader: 本体加载器实例
        """
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
        1. 查找动作定义
        2. 调用对象动作执行
        3. 查询类动作应用溢出处理
        4. 格式化为 MCP 返回格式
        
        Args:
            object_code: 对象代码
            action_code: 动作代码
            arguments: 动作参数
        
        Returns:
            dict: MCP 格式的执行结果
        
        Raises:
            ActionNotFoundError: 动作不存在时抛出
        """
        cls = self._loader.get_ontology_class(object_code)
        action = None
        for a in cls.actions:
            if a.action_code == action_code:
                action = a
                break
        if action is None:
            from datacloud_data_sdk.exceptions import ActionNotFoundError

            raise ActionNotFoundError(object_code, action_code)

        obj = self._loader.get_object(object_code)
        result = await obj.invoke_action(action_code, arguments)

        # 查询类动作（is_virtual 或 action_type=query）且 result 含 records+meta 时，数据量大则存 CSV
        is_query_action = getattr(action, "is_virtual", False) or getattr(
            action, "action_type", ""
        ) == "query"
        has_records_meta = "records" in result and "meta" in result
        if is_query_action and has_records_meta:
            result = _apply_overflow_if_query(result, self._loader)

        return {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
            ],
            "isError": False,
        }
