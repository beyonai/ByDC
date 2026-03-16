"""UnifiedQuery: unified_data_query 工具封装。"""

from __future__ import annotations

import json
from typing import Any

from datacloud_data.csv_storage.manager import CsvStorageManager
from datacloud_data.ontology.loader import OntologyLoader
from datacloud_data_service.tools.query_result_overflow import apply_query_result_overflow


def _apply_overflow_if_needed(result: dict[str, Any]) -> dict[str, Any]:
    """若 records 超阈值，则存 CSV 并返回元数据+下载地址+预览。"""
    if "records" not in result:
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


class UnifiedQuery:
    """统一数据查询工具，封装 View.query() 或 Object.query()。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    async def execute(
        self,
        question: str,
        view_id: str = "",
        object_ids: list[str] | None = None,
        include_plan: bool = True,
    ) -> dict[str, Any]:
        """执行自然语言查询，返回 MCP content 格式。"""
        try:
            if view_id:
                view = self._loader.get_view(view_id)
                result = await view.query(question, include_plan=include_plan)
            elif object_ids and len(object_ids) == 1:
                obj = self._loader.get_object(object_ids[0])
                result = await obj.query(question, include_plan=include_plan)
            else:
                all_ids = object_ids or [c.object_code for c in self._loader.get_ontology_classes()]
                from datacloud_data.view import View
                from datacloud_data.relation import Relation

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

            # 数据量大时存 CSV，返回元数据+下载地址+前 N 行预览
            result = _apply_overflow_if_needed(result)

            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ],
                "isError": False,
            }
        except Exception as e:
            from datacloud_data.events.trace_logger import log_exception_stack

            log_exception_stack(e)
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }
