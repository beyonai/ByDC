"""ViewLookupExecutor：执行视图级 lookup_* 虚拟动作（多表 JOIN 明细查询）。

视图物理模型：
- 驱动表为 view.objects[0]，别名 t0
- 其余对象依次编号 t1, t2, ...
- 通过 relation.join_keys 生成 LEFT JOIN 条件
- 字段通过视图 mapping 的 source_object_code+source_object_column_code 定位物理表
"""

from __future__ import annotations

import re
from typing import Any

from datacloud_data_sdk.executor.view_executor_support import (
    build_filters_where as _support_build_filters_where,
)
from datacloud_data_sdk.executor.view_executor_support import (
    build_join_clauses as _support_build_join_clauses,
)
from datacloud_data_sdk.executor.view_executor_support import (
    build_view_execution_context,
    collect_required_objects,
    quote_identifier,
)
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

_PKEY_RE = re.compile(r"[^a-zA-Z0-9]")


def _safe_pkey(prefix: str, fc: str, idx: int) -> str:
    safe = _PKEY_RE.sub("_", fc)[:40]
    return f"{prefix}_{safe}_{idx}"


def _quote(ident: str, db_type: str) -> str:
    return quote_identifier(ident, db_type)


def _join_key_fields(join_key: dict[str, Any]) -> tuple[str, str]:
    from datacloud_data_sdk.executor.view_executor_support import join_key_fields

    return join_key_fields(join_key)


def _build_join_clauses(
    view: Any,
    db_type: str,
    required_objects: set[str] | None = None,
) -> list[str]:
    return _support_build_join_clauses(view, db_type, required_objects)


def _build_filters_where(
    filters: list[dict], field_to_alias_col: dict[str, tuple[str, str]], db_type: str
) -> tuple[str, dict]:
    return _support_build_filters_where(filters, field_to_alias_col, db_type, _safe_pkey)


class ViewLookupExecutor:
    """执行视图级 lookup 虚拟动作（多对象 LEFT JOIN 明细查询）。"""

    def __init__(self, loader: OntologyLoader, ds_manager: DataSourceManager | None = None) -> None:
        self._loader = loader
        self._ds = ds_manager or DataSourceManager(
            getattr(loader._config, "datasource_configs", None) or {}
        )

    async def execute(self, view: Any, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行视图 lookup 查询。"""
        if not view.objects:
            return {"records": [], "total": 0, "meta": {"view_id": view.view_id}}

        context = build_view_execution_context(view, self._ds)
        alias = context.datasource_alias
        db_type = context.db_type
        field_to_alias_col = context.field_to_alias_col

        # select
        select_codes = arguments.get("select") or list(field_to_alias_col.keys())
        select_parts = []
        col_keys = []
        for fc in select_codes:
            resolved = field_to_alias_col.get(fc)
            if resolved:
                ta, col = resolved
                select_parts.append(f"{ta}.{_quote(col, db_type)} AS {_quote(fc, db_type)}")
                col_keys.append(fc)

        if not select_parts:
            select_parts = ["t0.*"]
            col_keys = []

        # WHERE
        where_sql, params = _build_filters_where(
            arguments.get("filters") or [], field_to_alias_col, db_type
        )

        # ORDER BY
        order_clauses: list[str] = []
        for ob in arguments.get("order_by") or []:
            fc = ob.get("field", "")
            direction = ob.get("direction", "asc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "ASC"
            resolved = field_to_alias_col.get(fc)
            if resolved:
                ta, col = resolved
                order_clauses.append(f"{ta}.{_quote(col, db_type)} {direction}")

        required_fields = set(select_codes)
        required_fields.update(item.get("field", "") for item in arguments.get("filters") or [])
        required_fields.update(item.get("field", "") for item in arguments.get("order_by") or [])
        required_fields.discard("")

        # JOIN
        join_clauses = _support_build_join_clauses(
            view,
            db_type,
            collect_required_objects(view, context.field_to_object_code, required_fields),
        )

        limit = int(arguments.get("limit") or 100)
        offset = int(arguments.get("offset") or 0)

        # 拼接 SQL
        from_clause = f"{_quote(context.anchor_table, db_type)} t0"
        if join_clauses:
            from_clause += " " + " ".join(join_clauses)

        sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_clauses:
            sql += f" ORDER BY {', '.join(order_clauses)}"
        sql += f" LIMIT {limit} OFFSET {offset}"

        try:
            connector = self._ds.get_connector(alias)
            rows = await connector.execute(sql, params)
        except Exception as exc:
            raise RuntimeError(f"view lookup query failed: {exc}") from exc

        records = [
            dict(zip(col_keys, row, strict=False)) if isinstance(row, (list, tuple)) else row
            for row in rows
        ]
        return {
            "records": records,
            "total": len(records),
            "meta": {"view_id": view.view_id, "columns": col_keys},
        }
