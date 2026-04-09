"""KbSearchExecutor：执行 search_* 虚拟动作（知识库语义检索）。

协议格式（新）：
{
  "query": "检索文本",
  "filters": [{"field": "...", "op": "...", "value": ...}],
  "limit": 20
}
"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader


class KbSearchExecutor:
    """执行知识库对象的 search_* 虚拟动作。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    async def execute(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行 search 动作。当前为占位实现，返回空结果。
        实际向量检索通过 KbExecutor（配置了 kb_source_configs 时）路由。

        Args:
            object_code: 对象编码
            arguments: search 协议参数 {query, filters, limit}

        Returns:
            {"records": [], "total": 0, "meta": {...}}
        """
        cls = self._loader.get_ontology_class(object_code)

        # 尝试通过 kb_source_configs 执行向量检索
        kb_configs = getattr(self._loader._config, "kb_source_configs", None)
        if kb_configs and cls.datasource_alias and cls.datasource_alias in kb_configs:
            try:
                return await self._execute_kb(cls, arguments, kb_configs)
            except Exception:
                pass

        # 占位：返回空
        return {
            "records": [],
            "total": 0,
            "meta": {
                "object_code": object_code,
                "query": arguments.get("query", ""),
                "note": "kb_source_configs not configured or search not implemented",
            },
        }

    async def _execute_kb(
        self, cls: Any, arguments: dict[str, Any], kb_configs: dict
    ) -> dict[str, Any]:
        """通过 KbExecutor 执行向量检索（需要 kb_source_configs 配置）。"""
        from datacloud_data_sdk.executor.kb_executor import KbExecutor

        executor = KbExecutor(kb_configs)
        query = arguments.get("query", "")
        filters = arguments.get("filters") or []
        limit = int(arguments.get("limit") or 20)

        # 转换 filters 为旧格式（KbExecutor 期望 dict 格式）
        legacy_filters: dict[str, Any] = {}
        for item in filters:
            fc = item.get("field", "")
            op = item.get("op", "eq")
            value = item.get("value")
            if fc and op == "eq":
                legacy_filters[fc] = {"op": "eq", "value": value}

        result = await executor.search(
            object_code=cls.object_code,
            query=query,
            filters=legacy_filters,
            limit=limit,
        )
        return result
