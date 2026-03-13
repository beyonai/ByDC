"""DynamicQueryExecutor: 执行 query_{object_code} 虚拟动作。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.executor.db_sql_builder import build_select_sql, build_where_clause
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


def _resolve_source_column(field: Any, datasource_alias: str) -> str:
    """解析字段物理列名，无则用 field_code。"""
    if field.source_column:
        return field.source_column
    for m in getattr(field, "physical_mappings", []):
        if m.source_type == "DB" and m.datasource_alias == datasource_alias:
            return m.source_ref
    return field.field_code


def _build_meta_columns(
    col_keys: list[str],
    cls: Any,
    aggregates: list[dict[str, Any]] | None,
    group_by: list[str],
) -> list[dict[str, str]]:
    """根据 col_keys 构建 meta.columns，每项 {name, label, type}。"""
    field_map = {f.field_code: f for f in cls.fields}
    columns: list[dict[str, str]] = []

    if not aggregates:
        for key in col_keys:
            f = field_map.get(key)
            columns.append({
                "name": key,
                "label": f.field_name if f else key,
                "type": (f.field_type or "string").lower(),
            })
    elif group_by:
        for key in group_by:
            f = field_map.get(key)
            columns.append({
                "name": key,
                "label": f.field_name if f else key,
                "type": (f.field_type or "string").lower(),
            })
        for agg in aggregates or []:
            alias = agg.get("as") or f"{agg.get('func', 'count').lower()}_{agg.get('field', '')}"
            columns.append({"name": alias, "label": alias, "type": "number"})
    else:
        for agg in aggregates or []:
            alias = agg.get("as") or f"{agg.get('func', 'count').lower()}_{agg.get('field', '')}"
            columns.append({"name": alias, "label": alias, "type": "number"})

    return columns


class DynamicQueryExecutor:
    """执行 DB/KB 对象的 query_{object_code} 虚拟动作。返回原始数据，由调用方包装为 MCP content。"""

    def __init__(
        self,
        loader: OntologyLoader,
        ds_manager: DataSourceManager | None = None,
    ) -> None:
        self._loader = loader
        self._ds = ds_manager or DataSourceManager(
            getattr(loader._config, "datasource_configs", None) or {}
        )

    async def execute(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """执行虚拟查询动作，返回原始数据 {"records": [], "total": 0}。"""
        cls = self._loader.get_ontology_class(object_code)
        if cls.source_type == "DB":
            return await self._execute_db(object_code, cls, arguments)
        if cls.source_type == "KNOWLEDGE_BASE":
            return await self._execute_kb(object_code, cls, arguments)
        raise ValueError(f"Unsupported source_type: {cls.source_type}")

    async def _execute_db(
        self, object_code: str, cls: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """DB 类型：根据 filters/aggregates/group_by 生成 SQL 并执行。"""
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")
        alias = cls.datasource_alias
        if not alias:
            raise ValueError(f"Object {object_code} missing datasource_alias")

        try:
            connector = self._ds.get_connector(alias)
        except DataSourceUnavailableError:
            raise

        datasource_alias = alias or ""
        field_to_col = {f.field_code: _resolve_source_column(f, datasource_alias) for f in cls.fields}

        filters = arguments.get("filters") or {}
        aggregates = arguments.get("aggregates")
        group_by = arguments.get("group_by") or []

        where_sql, where_params = build_where_clause(filters, field_to_col)

        db_type = "SQLITE"
        if cls.source_config and isinstance(cls.source_config, dict):
            db_type = cls.source_config.get("db_type", "SQLITE")

        fields: list[tuple[str, str]] = [(f.field_code, field_to_col[f.field_code]) for f in cls.fields]
        sql, col_keys = build_select_sql(
            table=cls.table_name,
            fields=fields,
            aggregates=aggregates,
            group_by=group_by if group_by else None,
            where_sql=where_sql,
            db_type=db_type,
            field_to_col=field_to_col,
        )

        records = await connector.execute(sql, where_params or None)
        total = len(records)
        columns = _build_meta_columns(col_keys, cls, aggregates, group_by)
        return {
            "records": records,
            "total": total,
            "meta": {
                "viewId": "auto_view",
                "columns": columns,
                "total": total,
            },
        }

    async def _execute_kb(
        self, object_code: str, cls: Any, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """KB 类型：根据 query/filters 调用 RAG 检索。"""
        # TODO: 实现 query + filters -> KB 检索
        # 当前返回占位，后续接入 kb_executor
        return {
            "records": [],
            "total": 0,
            "meta": {"viewId": "auto_view", "columns": [], "total": 0},
        }
