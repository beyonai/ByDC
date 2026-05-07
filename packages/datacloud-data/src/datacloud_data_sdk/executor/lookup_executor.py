"""LookupExecutor：执行 lookup_* 虚拟动作（单对象明细查询）。

协议格式（新）：
{
  "select": ["field_code", ...],          // 可选
  "filters": [{"field": "...", "op": "...", "value": ...}],
  "order_by": [{"field": "...", "direction": "asc|desc"}],
  "limit": 100,
  "offset": 0
}
"""

from __future__ import annotations

import re
from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.result_term_converter import ResultTermConverter
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

_PKEY_RE = re.compile(r"[^a-zA-Z0-9]")


def _safe_pkey(prefix: str, fc: str, idx: int) -> str:
    """生成安全的 SQL 命名参数键（仅含字母数字下划线）。"""
    safe = _PKEY_RE.sub("_", fc)[:40]
    return f"{prefix}_{safe}_{idx}"


def _resolve_source_column(field: Any, datasource_alias: str) -> str:
    if field.source_column:
        return field.source_column
    for m in getattr(field, "physical_mappings", []):
        if m.source_type == "DB" and m.datasource_alias == datasource_alias:
            return m.source_ref
    return field.field_code


def _quote(ident: str, db_type: str) -> str:
    dt = db_type.upper()
    if dt in ("POSTGRESQL", "OPENGAUSS", "SQLITE"):
        return f'"{ident}"'
    if dt in ("MYSQL", "CLICKHOUSE"):
        return f"`{ident}`"
    return ident


def _build_filters_from_list(
    filters: list[dict[str, Any]],
    field_to_col: dict[str, str],
    db_type: str,
) -> tuple[str, dict[str, Any]]:
    """
    将新协议 filters 数组转换为 WHERE SQL。

    支持：eq / in / gt / gte / lt / lte / like / between / is_null / is_not_null
    """
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}
    q = lambda x: _quote(x, db_type)

    for idx, item in enumerate(filters):
        fc = item.get("field", "")
        op = item.get("op", "eq")
        value = item.get("value")
        col = field_to_col.get(fc, fc)
        pkey = _safe_pkey("p", fc, idx)

        if op == "is_null":
            clauses.append(f"{q(col)} IS NULL")
        elif op == "is_not_null":
            clauses.append(f"{q(col)} IS NOT NULL")
        elif op == "between":
            vals = value if isinstance(value, list) else [value, value]
            clauses.append(f"{q(col)} BETWEEN :{pkey}_0 AND :{pkey}_1")
            params[f"{pkey}_0"] = vals[0]
            params[f"{pkey}_1"] = vals[1]
        elif op == "in":
            vals = value if isinstance(value, list) else [value]
            pkeys = [f"{pkey}_{i}" for i in range(len(vals))]
            placeholders = ", ".join(f":{k}" for k in pkeys)
            clauses.append(f"{q(col)} IN ({placeholders})")
            for k, v in zip(pkeys, vals):
                params[k] = v
        elif op == "like":
            # 若 value 不含通配符，自动补 %...% 实现 contains 语义
            like_val = value if (isinstance(value, str) and "%" in value) else f"%{value}%"
            clauses.append(f"{q(col)} LIKE :{pkey}")
            params[pkey] = like_val
        else:
            # eq / gt / gte / lt / lte
            op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            clauses.append(f"{q(col)} {op_map.get(op, '=')} :{pkey}")
            params[pkey] = value

    return " AND ".join(clauses), params


class LookupExecutor:
    """执行单对象 lookup 虚拟动作。"""

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

    async def execute(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行 lookup 动作。

        Args:
            object_code: 对象编码
            arguments: 符合新协议格式的输入参数

        Returns:
            {"records": [...], "total": int, "meta": {...}}
        """
        cls = self._loader.get_ontology_class(object_code)
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")

        alias = cls.datasource_alias or ""
        config = self._ds._configs.get(alias) if alias else None
        db_type = getattr(config, "db_type", "SQLITE") if config else "SQLITE"
        q = lambda x: _quote(x, db_type)

        # 过滤出物理字段（排除 derived/linked）
        physical_fields = [
            f
            for f in cls.fields
            if getattr(f, "property_kind", "physical") not in ("derived", "linked")
        ]
        field_to_col = {f.field_code: _resolve_source_column(f, alias) for f in physical_fields}
        field_map = {f.field_code: f for f in cls.fields}

        # select 字段
        select_codes = arguments.get("select") or [f.field_code for f in physical_fields]
        select_pairs = [(fc, field_to_col[fc]) for fc in select_codes if fc in field_to_col]
        if not select_pairs:
            select_pairs = list(field_to_col.items())

        # WHERE
        filters = arguments.get("filters") or []
        where_sql, params = _build_filters_from_list(filters, field_to_col, db_type)

        # ORDER BY
        order_clauses: list[str] = []
        for ob in arguments.get("order_by") or []:
            fc = ob.get("field", "")
            direction = ob.get("direction", "asc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "ASC"
            col = field_to_col.get(fc, fc)
            order_clauses.append(f"{q(col)} {direction}")

        # LIMIT / OFFSET
        limit = int(arguments.get("limit") or 100)
        offset = int(arguments.get("offset") or 0)

        # 构建 SQL
        table = cls.table_name
        select_exprs = ", ".join(f"{q(col)} AS {q(fc)}" for fc, col in select_pairs)
        sql = f"SELECT {select_exprs} FROM {q(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_clauses:
            sql += f" ORDER BY {', '.join(order_clauses)}"
        sql += f" LIMIT {limit} OFFSET {offset}"

        try:
            connector = self._ds.get_connector(alias)
            rows = await connector.execute(sql, params)
        except DataSourceUnavailableError:
            raise
        except Exception as exc:
            raise RuntimeError(f"lookup query failed: {exc}") from exc

        col_keys = [fc for fc, _ in select_pairs]
        records = [
            dict(zip(col_keys, row)) if isinstance(row, (list, tuple)) else row for row in rows
        ]
        records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(
            records,
            [field_map[fc] for fc in col_keys if fc in field_map],
        )

        # meta.columns
        columns = [
            {
                "name": fc,
                "label": getattr(field_map.get(fc), "field_name", fc),
                "type": (getattr(field_map.get(fc), "field_type", "string") or "string").lower(),
            }
            for fc in col_keys
        ]

        return {
            "records": records,
            "total": len(records),
            "meta": {"columns": columns, "object_code": object_code},
        }
