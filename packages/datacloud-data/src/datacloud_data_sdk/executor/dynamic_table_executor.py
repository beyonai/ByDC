"""Dynamic table virtual action executor."""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.executor.param_coercion import coerce_sql_param
from datacloud_data_sdk.executor.query_executor import (
    _build_where,
    _quote,
    _resolve_select_expr,
)
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.term_resolver import TermResolver
from datacloud_data_sdk.result_term_converter import ResultTermConverter
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


class DynamicTableExecutor:
    """Execute insert/update/delete virtual actions for DYNAMIC_TABLE objects."""

    def __init__(
        self,
        loader: OntologyLoader,
        ds_manager: DataSourceManager | None = None,
    ) -> None:
        self._loader = loader
        self._ds = ds_manager or DataSourceManager(
            getattr(loader._config, "datasource_configs", None) or {},
            fallback_loader=loader,
        )

    async def insert(self, object_code: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Insert one or more dynamic-table rows."""
        cls = self._get_dynamic_class(object_code)
        records = arguments.get("records") or []
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list) or not records:
            raise ValueError("insert records must be a non-empty list")

        fields = self._writable_fields(cls, include_primary_key=False)
        field_map = {field.field_code: field for field in fields}
        db_type = self._get_db_type(cls)
        connector = self._ds.get_connector(cls.datasource_alias or "")
        inserted_records: list[dict[str, Any]] = []

        for raw_record in records:
            if not isinstance(raw_record, dict):
                raise ValueError("insert record must be an object")
            record = self._resolve_value_terms(raw_record, field_map)
            self._validate_known_fields(record, field_map, "insert")
            columns = [field_map[field_code] for field_code in record if field_code in field_map]
            if not columns:
                raise ValueError("insert record has no writable fields")

            params: dict[str, Any] = {}
            quoted_columns: list[str] = []
            placeholders: list[str] = []
            for idx, field in enumerate(columns):
                param_name = f"v_{idx}"
                quoted_columns.append(_quote(field.source_column or field.field_code, db_type))
                placeholders.append(f":{param_name}")
                params[param_name] = coerce_sql_param(record[field.field_code], field)

            sql = (
                f"INSERT INTO {_quote(cls.table_name or '', db_type)} "
                f"({', '.join(quoted_columns)}) VALUES ({', '.join(placeholders)})"
            )
            returned_rows = await connector.execute(sql, params)
            if returned_rows:
                inserted_records.extend(
                    _normalize_rows(returned_rows, [f.field_code for f in columns])
                )
            else:
                inserted_records.append(dict(record))

        return self._response(cls, inserted_records)

    async def update(self, object_code: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Update dynamic-table rows and return updated row data."""
        cls = self._get_dynamic_class(object_code)
        values = arguments.get("values") or {}
        if not isinstance(values, dict) or not values:
            raise ValueError("update values must be a non-empty object")

        filters = self._normalize_filters(arguments.get("filters") or [])
        if not filters:
            raise ValueError("update filters are required")

        fields = self._writable_fields(cls, include_primary_key=False)
        all_fields = self._readable_fields(cls)
        field_map = {field.field_code: field for field in all_fields}
        writable_map = {field.field_code: field for field in fields}
        resolved_values = self._resolve_value_terms(values, writable_map)
        self._validate_known_fields(resolved_values, writable_map, "update")
        resolved_filters = self._resolve_filter_terms(filters, field_map)
        db_type = self._get_db_type(cls)
        where_sql, params = _build_where(
            resolved_filters,
            field_map,
            db_type,
            str(arguments.get("filter_relation") or "AND"),
        )
        if not where_sql:
            raise ValueError("update filters are required")

        set_parts: list[str] = []
        for idx, (field_code, value) in enumerate(resolved_values.items()):
            field = writable_map[field_code]
            param_name = f"u_{idx}"
            set_parts.append(
                f"{_quote(field.source_column or field.field_code, db_type)} = :{param_name}"
            )
            params[param_name] = coerce_sql_param(value, field)

        connector = self._ds.get_connector(cls.datasource_alias or "")
        sql = (
            f"UPDATE {_quote(cls.table_name or '', db_type)} "
            f"SET {', '.join(set_parts)} WHERE {where_sql}"
        )
        await connector.execute(sql, params)
        records = await self._select_rows(
            cls, resolved_filters, str(arguments.get("filter_relation") or "AND")
        )
        return self._response(cls, records)

    async def delete(self, object_code: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Physically delete dynamic-table rows and return pre-delete row data."""
        cls = self._get_dynamic_class(object_code)
        filters = self._normalize_filters(arguments.get("filters") or [])
        if not filters:
            raise ValueError("delete filters are required")

        field_map = {field.field_code: field for field in self._readable_fields(cls)}
        resolved_filters = self._resolve_filter_terms(filters, field_map)
        filter_relation = str(arguments.get("filter_relation") or "AND")
        records = await self._select_rows(cls, resolved_filters, filter_relation)
        db_type = self._get_db_type(cls)
        where_sql, params = _build_where(resolved_filters, field_map, db_type, filter_relation)
        if not where_sql:
            raise ValueError("delete filters are required")

        connector = self._ds.get_connector(cls.datasource_alias or "")
        sql = f"DELETE FROM {_quote(cls.table_name or '', db_type)} WHERE {where_sql}"
        await connector.execute(sql, params)
        return self._response(cls, records)

    async def _select_rows(
        self,
        cls: Any,
        filters: list[dict[str, Any]],
        filter_relation: str,
    ) -> list[dict[str, Any]]:
        fields = self._readable_fields(cls)
        field_map = {field.field_code: field for field in fields}
        db_type = self._get_db_type(cls)
        select_exprs = ", ".join(_resolve_select_expr(field, db_type) for field in fields)
        where_sql, params = _build_where(filters, field_map, db_type, filter_relation)
        sql = f"SELECT {select_exprs} FROM {_quote(cls.table_name or '', db_type)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        connector = self._ds.get_connector(cls.datasource_alias or "")
        rows = await connector.execute(sql, params)
        return _normalize_rows(rows, [field.field_code for field in fields])

    def _get_dynamic_class(self, object_code: str) -> Any:
        cls = self._loader.get_ontology_class(object_code)
        if str(getattr(cls, "source_type", "") or "").upper() != "DYNAMIC_TABLE":
            raise ValueError(f"Object {object_code} is not a dynamic table")
        if not getattr(cls, "table_name", None):
            raise ValueError(f"Object {object_code} missing table_name")
        if not getattr(cls, "datasource_alias", None):
            raise ValueError(f"Object {object_code} missing datasource_alias")
        return cls

    def _get_db_type(self, cls: Any) -> str:
        alias = str(getattr(cls, "datasource_alias", "") or "")
        config = self._ds._configs.get(alias)
        if config is not None:
            return str(getattr(config, "db_type", "") or "SQLITE")
        source_config = getattr(cls, "source_config", None)
        if isinstance(source_config, dict):
            return str(source_config.get("db_type") or "SQLITE")
        return "SQLITE"

    @staticmethod
    def _readable_fields(cls: Any) -> list[Any]:
        return [
            field
            for field in getattr(cls, "fields", [])
            if getattr(field, "property_kind", "physical") == "physical"
        ]

    @classmethod
    def _writable_fields(cls, target_cls: Any, *, include_primary_key: bool) -> list[Any]:
        return [
            field
            for field in cls._readable_fields(target_cls)
            if include_primary_key or not getattr(field, "is_primary_key", False)
        ]

    @staticmethod
    def _normalize_filters(filters: Any) -> list[dict[str, Any]]:
        if isinstance(filters, dict):
            return [
                {"field": field_code, **spec}
                if isinstance(spec, dict)
                else {"field": field_code, "op": "eq", "value": spec}
                for field_code, spec in filters.items()
            ]
        if isinstance(filters, list):
            return [item for item in filters if isinstance(item, dict)]
        return []

    def _resolve_value_terms(
        self,
        values: dict[str, Any],
        field_map: dict[str, Any],
    ) -> dict[str, Any]:
        term_loader = getattr(self._loader._config, "term_loader", None)
        if term_loader is None:
            return dict(values)

        resolver = TermResolver(term_loader)
        resolved = dict(values)
        for field_code, value in values.items():
            field = field_map.get(str(field_code))
            if field is None or not getattr(field, "term_set", None):
                continue
            resolved_filter = resolver.resolve_filter_values(
                [{"field": field.field_code, "op": "eq", "value": value}],
                [field],
            )
            if isinstance(resolved_filter, list) and resolved_filter:
                resolved[field_code] = resolved_filter[0].get("value")
        return resolved

    def _resolve_filter_terms(
        self,
        filters: list[dict[str, Any]],
        field_map: dict[str, Any],
    ) -> list[dict[str, Any]]:
        term_loader = getattr(self._loader._config, "term_loader", None)
        if term_loader is None:
            return filters

        return TermResolver(term_loader).resolve_filter_values(filters, list(field_map.values()))

    @staticmethod
    def _validate_known_fields(
        values: dict[str, Any],
        field_map: dict[str, Any],
        operation: str,
    ) -> None:
        unknown = [field_code for field_code in values if field_code not in field_map]
        if unknown:
            raise ValueError(
                f"{operation} contains unknown or readonly fields: {', '.join(unknown)}"
            )

    def _response(self, cls: Any, records: list[dict[str, Any]]) -> dict[str, Any]:
        fields = self._readable_fields(cls)
        converted_records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(records, fields)
        columns = [
            {
                "name": field.field_code,
                "label": field.field_name,
                "type": str(getattr(field, "field_type", "STRING") or "STRING").lower(),
            }
            for field in fields
        ]
        return {
            "records": converted_records,
            "total": len(converted_records),
            "meta": {"columns": columns, "object_code": cls.object_code},
        }


def _normalize_rows(rows: list[Any], keys: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            records.append(dict(row))
        elif isinstance(row, (list, tuple)):
            records.append(dict(zip(keys, row)))
    return records
