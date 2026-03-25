"""
动态查询执行器模块

本模块提供虚拟动作的查询执行能力，根据对象定义动态构建 SQL 查询。
支持字段过滤、分页、聚合、关联查询等功能。

核心功能：
- 动态构建 SELECT SQL 语句
- 支持 WHERE 条件过滤
- 支持分页查询（page, page_size）
- 支持聚合查询（group_by, aggregates）
- 支持关联对象查询（linked_joins）

使用示例：
    executor = DynamicQueryExecutor(loader)
    result = await executor.execute("po_users", {
        "filters": {"status": "active"},
        "page": 1,
        "page_size": 20
    })
"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.executor.db_sql_builder import build_select_sql, build_where_clause
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


def _resolve_source_column(field: Any, datasource_alias: str) -> str:
    """
    解析字段的物理列名
    
    优先使用 source_column，其次查找 physical_mappings 中的映射，
    最后使用 field_code 作为默认值。
    
    Args:
        field: 字段定义对象
        datasource_alias: 数据源别名
    
    Returns:
        str: 物理列名
    """
    if field.source_column:
        return field.source_column
    for m in getattr(field, "physical_mappings", []):
        if m.source_type == "DB" and m.datasource_alias == datasource_alias:
            return m.source_ref
    return field.field_code


def _group_linked_records(
    flat_records: list[dict[str, Any]],
    col_keys: list[str],
    physical_fields: list[Any],
    linked_joins: list[dict[str, Any]],
    cls: Any,
) -> list[dict[str, Any]]:
    """
    将 LEFT JOIN 产生的扁平行按主表键分组
    
    当查询包含关联对象时，SQL 使用 LEFT JOIN 产生扁平化的行，
    此函数将同一主表记录的关联数据聚合成列表。
    
    Args:
        flat_records: 扁平化的记录列表
        col_keys: 列名列表
        physical_fields: 物理字段列表
        linked_joins: 关联连接配置
        cls: 本体类定义
    
    Returns:
        list[dict]: 分组后的记录列表，关联字段为嵌套列表
    """
    main_cols = {f.field_code for f in physical_fields}
    pk_field = next((f.field_code for f in cls.fields if getattr(f, "is_primary_key", False)), None)
    group_key_field = pk_field or (linked_joins[0].get("join_from", "") if linked_joins else None)
    if not group_key_field:
        return flat_records

    # 构建 linked_field -> {prefixed_key -> field_code} 映射
    linked_field_map: dict[str, dict[str, str]] = {}
    for lj in linked_joins:
        lf = lj.get("linked_field", "")
        linked_field_map[lf] = {
            f"{lf}_{fc}": fc for fc, _ in lj.get("target_fields", [])
        }

    groups: dict[Any, dict[str, Any]] = {}
    for row in flat_records:
        key = row.get(group_key_field)
        if key not in groups:
            main_row = {k: row[k] for k in main_cols if k in row}
            groups[key] = {**main_row, **{lf: [] for lf in linked_field_map}}
        parent = groups[key]

        for lf, prefixed_to_fc in linked_field_map.items():
            target_row = {fc: row.get(prefixed) for prefixed, fc in prefixed_to_fc.items()}
            if any(v is not None for v in target_row.values()):
                parent[lf].append(target_row)

    return list(groups.values())


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
        # 仅 physical 字段参与 field_to_col 与 fields；derived、linked 不参与
        physical_fields = [
            f for f in cls.fields
            if getattr(f, "property_kind", "physical") not in ("derived", "linked")
        ]
        field_to_col = {f.field_code: _resolve_source_column(f, datasource_alias) for f in physical_fields}

        filters = arguments.get("filters") or {}
        aggregates = arguments.get("aggregates")
        group_by = arguments.get("group_by") or []
        limit = arguments.get("limit")
        offset = arguments.get("offset")

        where_sql, where_params = build_where_clause(filters, field_to_col)

        db_type = "SQLITE"
        if cls.source_config and isinstance(cls.source_config, dict):
            db_type = cls.source_config.get("db_type", "SQLITE")

        fields: list[tuple[str, str]] = [(f.field_code, field_to_col[f.field_code]) for f in physical_fields]

        # 收集 derived 字段：expression 与 aggregation
        derived_expressions: list[tuple[str, str]] = []
        derived_aggregations: list[dict[str, Any]] = []
        for f in cls.fields:
            if getattr(f, "property_kind", "physical") != "derived":
                continue
            dc = getattr(f, "derived_config", None) or {}
            mode = dc.get("mode")
            if mode == "expression":
                expr = dc.get("expression")
                if expr:
                    derived_expressions.append((f.field_code, expr))
            elif mode == "aggregation":
                relation_ref = dc.get("relation_ref")
                if not relation_ref:
                    continue
                rel = next(
                    (r for r in self._loader.get_ontology_relations() if r.relation_code == relation_ref),
                    None,
                )
                if not rel or not rel.join_keys:
                    continue
                target_cls = self._loader.get_ontology_class(rel.target_class)
                # 仅当 target 与 source 同源时才加入 derived_aggregations
                if target_cls.datasource_alias != datasource_alias:
                    continue
                target_table = target_cls.table_name or rel.target_class
                jk = rel.join_keys[0]
                derived_aggregations.append({
                    "alias": f.field_code,
                    "target_table": target_table,
                    "target_field": dc.get("target_field", "id"),
                    "func": dc.get("func", "count"),
                    "join_from": jk.get("from_field", ""),
                    "join_to": jk.get("to_field", ""),
                })

        # 收集同源 linked 字段，构建 linked_joins
        linked_joins: list[dict[str, Any]] = []
        for f in cls.fields:
            if getattr(f, "property_kind", "physical") != "linked":
                continue
            relation_ref = getattr(f, "relation_ref", None)
            if not relation_ref:
                continue
            rel = next(
                (r for r in self._loader.get_ontology_relations() if r.relation_code == relation_ref),
                None,
            )
            if not rel or not rel.join_keys:
                continue
            target_cls = self._loader.get_ontology_class(rel.target_class)
            if target_cls.datasource_alias != datasource_alias:
                continue
            target_table = target_cls.table_name or rel.target_class
            jk = rel.join_keys[0]
            join_from = jk.get("from_field", "")
            join_to = jk.get("to_field", "")
            target_field_to_col = {
                tf.field_code: _resolve_source_column(tf, datasource_alias)
                for tf in target_cls.fields
                if getattr(tf, "property_kind", "physical") not in ("derived", "linked")
            }
            target_fields = [(fc, target_field_to_col[fc]) for fc in target_field_to_col]
            linked_joins.append({
                "linked_field": f.field_code,
                "target_table": target_table,
                "join_from": join_from,
                "join_to": join_to,
                "target_fields": target_fields,
            })

        sql, col_keys = build_select_sql(
            table=cls.table_name,
            fields=fields,
            aggregates=aggregates,
            group_by=group_by if group_by else None,
            where_sql=where_sql,
            db_type=db_type,
            field_to_col=field_to_col,
            derived_expressions=derived_expressions if derived_expressions else None,
            derived_aggregations=derived_aggregations if derived_aggregations else None,
            linked_joins=linked_joins if linked_joins else None,
            limit=limit,
            offset=offset,
        )

        records = await connector.execute(sql, where_params or None)

        # 若有 linked_joins，扁平行按主表 key 分组，target 聚合成 list[dict]
        if linked_joins:
            records = _group_linked_records(
                records,
                col_keys,
                physical_fields,
                linked_joins,
                cls,
            )
            # 分组后 col_keys 需排除 prefixed 列，追加 linked 字段名
            linked_prefixes = {f"{lj.get('linked_field', '')}_{fc}" for lj in linked_joins for fc, _ in lj.get("target_fields", [])}
            col_keys = [k for k in col_keys if k not in linked_prefixes] + [lj.get("linked_field", "") for lj in linked_joins]

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
