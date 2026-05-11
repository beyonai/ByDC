"""视图多数据源 DB 联邦执行器。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from datacloud_data_sdk.executor.local_federation_engine import (
    LocalFederationRuntime,
    LocalFederationTable,
    create_local_federation_engine,
)
from datacloud_data_sdk.executor.view_executor_support import join_key_fields, quote_identifier
from datacloud_data_sdk.executor.view_federation_support import (
    ViewRequestPlan,
    build_join_edges,
    build_view_slice,
    collect_pushdown_filters,
)
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

_FORMULA_KINDS = frozenset({"derived_metric", "formula_metric", "virtual_tag"})


def _sqlite_type(field_type: str | None) -> str:
    """将本体字段类型映射为 SQLite 列类型。"""
    normalized = str(field_type or "").upper()
    if normalized in {"INTEGER", "INT", "BIGINT", "LONG"}:
        return "INTEGER"
    if normalized in {"NUMBER", "DECIMAL", "DOUBLE", "FLOAT"}:
        return "REAL"
    if normalized == "BOOLEAN":
        return "INTEGER"
    return "TEXT"


def _field_by_code(cls: Any, column_code: str) -> Any | None:
    """按 field_code/source_column 查找对象字段。"""
    for field in getattr(cls, "fields", []):
        if field.field_code == column_code or getattr(field, "source_column", None) == column_code:
            return field
    return None


def _object_db_type(ds_manager: DataSourceManager, datasource_alias: str) -> str:
    """获取对象数据源类型。"""
    config = ds_manager._configs.get(datasource_alias) if datasource_alias else None
    return str(getattr(config, "db_type", "SQLITE") if config else "SQLITE")


def _source_select_expression(cls: Any, column_code: str, db_type: str) -> str:
    """生成远端对象列查询表达式。"""
    field = _field_by_code(cls, column_code)
    alias = quote_identifier(column_code, db_type)
    if field is None:
        return f"{quote_identifier(column_code, db_type)} AS {alias}"

    formula = getattr(field, "formula", None)
    analytic_kind = getattr(field, "analytic_kind", None)
    if formula and analytic_kind in _FORMULA_KINDS:
        return f"({formula}) AS {alias}"

    source_column = getattr(field, "source_column", None) or getattr(
        field, "field_code", column_code
    )
    return f"{quote_identifier(source_column, db_type)} AS {alias}"


def _build_view_object_field_map(view: Any, object_code: str, loader: Any) -> dict[str, Any]:
    """构建视图属性到源对象字段的映射。"""
    source_cls = loader.get_ontology_class(object_code)
    field_map: dict[str, Any] = {
        field.field_code: field for field in getattr(source_cls, "fields", [])
    }

    for view_field in list(getattr(view, "fields", []) or []):
        source_object_code = str(getattr(view_field, "source_object_code", "") or "")
        if source_object_code != object_code:
            continue

        property_code = str(getattr(view_field, "property_code", "") or "")
        source_column_code = str(
            getattr(view_field, "source_object_column_code", "") or property_code
        )
        if not property_code or not source_column_code:
            continue

        source_field = _field_by_code(source_cls, source_column_code)
        if source_field is None:
            continue
        field_map[property_code] = replace(source_field, source_column=source_column_code)

    if field_map:
        return field_map
    return {field.field_code: field for field in getattr(source_cls, "fields", [])}


def _build_source_where_clause(
    mode: str,
    filters: list[dict[str, Any]],
    field_map: dict[str, Any],
    db_type: str,
    filter_relation: str,
) -> tuple[str, dict[str, Any]]:
    """生成源对象查询的 WHERE 子句。"""
    if not filters:
        return "", {}

    if mode == "compute":
        from datacloud_data_sdk.executor.compute_executor import _build_filters_where

        return _build_filters_where(filters, field_map, db_type, filter_relation)

    from datacloud_data_sdk.executor.query_executor import _build_where

    return _build_where(filters, field_map, db_type, filter_relation)


def _collect_required_columns(
    view: Any, object_codes: tuple[str, ...], referenced_fields: set[str]
) -> dict[str, set[str]]:
    """按对象收集联邦执行需要的源列。"""
    object_code_set = set(object_codes)
    columns = {object_code: set() for object_code in object_codes}

    for field in list(getattr(view, "fields", []) or []):
        object_code = str(getattr(field, "source_object_code", "") or "")
        field_code = str(getattr(field, "property_code", "") or "")
        source_column_code = str(
            getattr(field, "source_object_column_code", "")
            or getattr(field, "property_code", "")
            or ""
        )
        if (
            object_code in object_code_set
            and field_code in referenced_fields
            and source_column_code
        ):
            columns[object_code].add(source_column_code)

    for rel in getattr(view, "relations", []) or []:
        source_object = getattr(rel, "from_object", "") or getattr(rel, "source_class", "")
        target_object = getattr(rel, "to_object", "") or getattr(rel, "target_class", "")
        if source_object not in object_code_set or target_object not in object_code_set:
            continue
        for join_key in getattr(rel, "join_keys", []) or []:
            left_field, right_field = join_key_fields(join_key)
            if left_field:
                columns[source_object].add(left_field)
            if right_field:
                columns[target_object].add(right_field)

    for object_code in object_codes:
        if columns[object_code]:
            continue
        obj = next(
            (
                item
                for item in getattr(view, "objects", []) or []
                if item.object_code == object_code
            ),
            None,
        )
        if obj is None:
            continue
        primary_key = next(
            (
                getattr(field, "source_column", None) or field.field_code
                for field in getattr(obj._cls, "fields", [])
                if getattr(field, "is_primary_key", False)
            ),
            "",
        )
        if primary_key:
            columns[object_code].add(primary_key)

    return columns


class FederatedViewExecutorBase:
    """视图联邦执行器基类。"""

    def __init__(self, loader: Any, ds_manager: DataSourceManager | None = None) -> None:
        self._loader = loader
        self._ds = ds_manager or DataSourceManager(
            getattr(loader._config, "datasource_configs", None) or {},
            fallback_loader=loader,
        )
        self._local_federation_engine = create_local_federation_engine(
            getattr(loader, "_config", None)
        )

    def _build_type_map(self, object_code: str, columns: list[str]) -> dict[str, str]:
        """构建对象列到 SQLite 类型的映射。"""
        cls = self._loader.get_ontology_class(object_code)
        return {
            column_code: _sqlite_type(getattr(_field_by_code(cls, column_code), "field_type", None))
            for column_code in columns
        }

    async def _fetch_object_rows(
        self,
        view: Any,
        object_code: str,
        required_columns: set[str],
        arguments: dict[str, Any],
        *,
        mode: str,
        join_key_filters: list[dict[str, Any]] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]], dict[str, str]]:
        """查询单个对象的原始数据并返回列定义。"""
        cls = self._loader.get_ontology_class(object_code)
        if cls.source_type != "DB":
            raise ValueError(f"Federated view execution only supports DB object, got {object_code}")
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")

        selected_columns = sorted(required_columns)
        if not selected_columns:
            selected_columns = sorted(
                (getattr(field, "source_column", None) or field.field_code)
                for field in getattr(cls, "fields", [])
                if getattr(field, "property_kind", "physical") != "linked"
            )
        if not selected_columns:
            raise ValueError(f"Object {object_code} has no columns for federated execution")

        datasource_alias = cls.datasource_alias or ""
        db_type = _object_db_type(self._ds, datasource_alias)
        field_map = _build_view_object_field_map(view, object_code, self._loader)
        pushdown_filters = collect_pushdown_filters(view, arguments).get(object_code, [])
        source_filters = [*pushdown_filters, *(join_key_filters or [])]
        where_sql, params = _build_source_where_clause(
            mode,
            source_filters,
            field_map,
            db_type,
            "AND",
        )

        connector = self._ds.get_connector(datasource_alias)
        table_sql = quote_identifier(cls.table_name, db_type)
        type_map = self._build_type_map(object_code, selected_columns)

        select_sql = ", ".join(
            _source_select_expression(cls, column_code, db_type) for column_code in selected_columns
        )
        sql = f"SELECT {select_sql} FROM {table_sql}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        rows = await connector.execute(sql, params)
        return selected_columns, rows, type_map

    def _join_key_filters_for_edge(
        self,
        parent_rows: list[dict[str, Any]],
        edge: Any,
    ) -> list[dict[str, Any]]:
        """根据父对象结果生成子对象 join-key 预热过滤条件。"""
        values = [
            row.get(edge.parent_field_code)
            for row in parent_rows
            if row.get(edge.parent_field_code) is not None
        ]
        if not values:
            return []
        unique_values = list(dict.fromkeys(values))
        return [{"field": edge.child_field_code, "op": "in", "value": unique_values}]

    async def _build_local_view(
        self,
        view: Any,
        plan: ViewRequestPlan,
        arguments: dict[str, Any],
        *,
        mode: str,
    ) -> tuple[Any, LocalFederationRuntime]:
        """构建联邦执行用的本地视图切片。"""
        required_columns = _collect_required_columns(
            view, plan.closure_object_codes, plan.referenced_fields
        )
        join_edges = build_join_edges(view, plan)
        edge_by_child = {edge.child_object_code: edge for edge in join_edges}
        table_payloads: dict[str, LocalFederationTable] = {}

        ordered_object_codes: list[str] = []
        if plan.anchor_object_code:
            ordered_object_codes.append(plan.anchor_object_code)
        ordered_object_codes.extend(
            object_code
            for object_code in plan.closure_object_codes
            if object_code != plan.anchor_object_code
        )

        for object_code in ordered_object_codes:
            join_key_filters: list[dict[str, Any]] = []
            if object_code != plan.anchor_object_code and object_code in edge_by_child:
                edge = edge_by_child[object_code]
                parent_payload = table_payloads.get(edge.parent_object_code)
                parent_rows = parent_payload.rows if parent_payload else []
                if not parent_rows:
                    columns = sorted(required_columns.get(object_code, set()))
                    table_payloads[object_code] = LocalFederationTable(
                        columns=columns,
                        rows=[],
                        column_types=self._build_type_map(object_code, columns),
                    )
                    continue
                join_key_filters = self._join_key_filters_for_edge(parent_rows, edge)

            columns, rows, type_map = await self._fetch_object_rows(
                view,
                object_code,
                required_columns.get(object_code, set()),
                arguments,
                mode=mode,
                join_key_filters=join_key_filters,
            )
            table_payloads[object_code] = LocalFederationTable(
                columns=columns,
                rows=rows,
                column_types=type_map,
            )

        local_runtime = self._local_federation_engine.materialize_tables(table_payloads)

        local_view = build_view_slice(
            view,
            plan.closure_object_codes,
            datasource_alias=local_runtime.datasource_alias,
            local_table_names=True,
        )
        return local_view, local_runtime


class FederatedViewLookupExecutor(FederatedViewExecutorBase):
    """多源视图 lookup 联邦执行器。"""

    async def execute(
        self,
        view: Any,
        arguments: dict[str, Any],
        plan: ViewRequestPlan,
    ) -> dict[str, Any]:
        """执行多源视图明细查询。"""
        from datacloud_data_sdk.executor.view_lookup_executor import ViewLookupExecutor

        local_view, local_runtime = await self._build_local_view(
            view,
            plan,
            arguments,
            mode="query",
        )

        try:
            executor = ViewLookupExecutor(self._loader, ds_manager=local_runtime.datasource_manager)
            return await executor._execute_direct(local_view, arguments)
        finally:
            await local_runtime.close()


class FederatedViewAnalyzeExecutor(FederatedViewExecutorBase):
    """多源视图 analyze 联邦执行器。"""

    async def execute(
        self,
        view: Any,
        arguments: dict[str, Any],
        plan: ViewRequestPlan,
    ) -> dict[str, Any]:
        """执行多源视图聚合查询。"""
        from datacloud_data_sdk.executor.view_analyze_executor import ViewAnalyzeExecutor

        local_view, local_runtime = await self._build_local_view(
            view,
            plan,
            arguments,
            mode="compute",
        )

        try:
            executor = ViewAnalyzeExecutor(
                self._loader, ds_manager=local_runtime.datasource_manager
            )
            return await executor._execute_direct(local_view, arguments)
        finally:
            await local_runtime.close()
