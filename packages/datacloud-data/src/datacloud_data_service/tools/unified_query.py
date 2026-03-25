"""
统一数据查询工具模块

本模块提供统一的数据查询接口，封装了 View 和 Object 的查询能力。
支持自然语言查询，自动处理查询结果溢出。

核心功能：
- 视图查询：基于预定义视图执行查询
- 对象查询：基于单个对象执行查询
- 自动视图：多对象自动构建视图查询
- 结果溢出处理：大数据量自动转 CSV

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

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_service.tools.query_result_overflow import (
    ResultType,
    apply_query_result_overflow,
)

logger = logging.getLogger(__name__)


def _apply_overflow_if_needed(result: dict[str, Any], result_type: ResultType = "normal") -> dict[str, Any]:
    """
    应用查询结果溢出处理
    
    当结果记录数超过阈值时，将数据存储为 CSV 文件，
    返回元数据、下载地址和预览数据。
    
    Args:
        result: 原始查询结果
        result_type: 结果类型（normal/rejected/ask_user）
    
    Returns:
        dict: 处理后的结果
    """
    if "records" not in result and result_type == "normal":
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
            result_type=result_type,
        )
    except Exception as e:
        logger.exception("查询结果溢出处理失败: %s", e)
        result["result_type"] = result_type
        return result


class UnifiedQuery:
    """
    统一数据查询工具
    
    封装 View.query() 和 Object.query()，提供统一的查询入口。
    
    Attributes:
        _loader: 本体加载器实例
    
    Example:
        query = UnifiedQuery(loader)
        result = await query.execute("查询销售额", view_id="sales_view")
    """

    def __init__(self, loader: OntologyLoader) -> None:
        """
        初始化统一查询工具
        
        Args:
            loader: 本体加载器实例
        """
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
        
        Args:
            question: 自然语言问题
            view_id: 视图 ID（可选）
            object_ids: 对象 ID 列表（可选）
            include_plan: 是否在结果中包含执行计划
            page: 页码
            page_size: 每页大小
        
        Returns:
            dict: MCP 格式的查询结果
        """
        from datacloud_data_sdk.exceptions import (
            CannotAnswerError,
            PlanGenerationError,
            PlanValidationError,
            TermAmbiguousError,
            TermNotFoundError,
        )

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

            result = _apply_overflow_if_needed(result, "normal")

            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except TermNotFoundError as e:
            result = {
                "overflow_notice": str(e),
                "trace": {
                    "question": question,
                    "view_id": view_id,
                },
            }
            result = _apply_overflow_if_needed(result, "ask_user")
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except TermAmbiguousError as e:
            result = {
                "overflow_notice": str(e),
                "trace": {
                    "question": question,
                    "view_id": view_id,
                },
            }
            result = _apply_overflow_if_needed(result, "ask_user")
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except CannotAnswerError as e:
            result = {
                "overflow_notice": str(e),
                "trace": {
                    "question": question,
                    "view_id": view_id,
                },
            }
            result = _apply_overflow_if_needed(result, "rejected")
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except (PlanGenerationError, PlanValidationError) as e:
            result = {
                "overflow_notice": str(e),
                "trace": {
                    "question": question,
                    "view_id": view_id,
                },
            }
            result = _apply_overflow_if_needed(result, "rejected")
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except Exception as e:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(e)
            result = {
                "overflow_notice": str(e),
                "trace": {
                    "question": question,
                    "view_id": view_id,
                },
            }
            result = _apply_overflow_if_needed(result, "rejected")
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
