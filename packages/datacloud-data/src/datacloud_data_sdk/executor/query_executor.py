"""QueryExecutor：执行 query_* 虚拟动作（单对象明细检索）。

协议格式（§3.2.2，字段编码版）：
{
  "select":          ["field_code", ...],              // 可选，空 = 全部字段
  "filters":         [{"field": "field_code", "op": "...", "value": ...}],
  "filter_relation": "AND" | "OR",                     // 默认 AND
  "order_by":        [{"field": "field_code", "direction": "asc|desc"}],
  "limit":           100,
  "offset":          0
}

特点：
- field 直接使用字段编码（field_code），无需 name_to_code 翻译
- 支持 derived_metric / formula_metric / virtual_tag 的 formula 展开
- 支持 filter_relation OR/AND
- 校验前置：linked 字段拦截、op 合法性、账期强制约束
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.result_term_converter import ResultTermConverter
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.virtual_action.validator import (
    VirtualActionValidator,
)

_PKEY_RE = re.compile(r"[^a-zA-Z0-9]")

# analytic_kind 中需要展开 formula 的类型
_FORMULA_KINDS = frozenset({"derived_metric", "formula_metric", "virtual_tag"})


def _safe_pkey(prefix: str, fc: str, idx: int) -> str:
    """生成安全的 SQL 命名参数键（仅含字母数字下划线）。"""
    safe = _PKEY_RE.sub("_", fc)[:40]
    return f"{prefix}_{safe}_{idx}"


def _quote(ident: str, db_type: str) -> str:
    dt = db_type.upper()
    if dt in ("POSTGRESQL", "OPENGAUSS", "SQLITE"):
        return f'"{ident}"'
    if dt in ("MYSQL", "CLICKHOUSE"):
        return f"`{ident}`"
    return ident


def _resolve_select_expr(f: Any, db_type: str) -> str:
    """SELECT 中的字段表达式。

    formula 类字段：展开为 (formula) AS "中文名"
    普通物理字段：  source_column AS field_code
    """
    formula = getattr(f, "formula", None)
    kind = getattr(f, "analytic_kind", None)
    if formula and kind in _FORMULA_KINDS:
        alias = _quote(f.field_name, db_type)
        return f"({formula}) AS {alias}"
    col = f.source_column or f.field_code
    return f"{_quote(col, db_type)} AS {_quote(f.field_code, db_type)}"


def _resolve_col_expr(f: Any) -> str:
    """WHERE / ORDER BY 中的字段表达式（不能引用 SELECT 别名）。

    formula 类字段：重新展开 (formula)
    普通字段：      source_column 或 field_code
    """
    formula = getattr(f, "formula", None)
    kind = getattr(f, "analytic_kind", None)
    if formula and kind in _FORMULA_KINDS:
        return f"({formula})"
    return f.source_column or f.field_code


def _coerce_param(value: object, f: object | None) -> object:
    """将字符串值按字段 analytic_kind 转换为正确的 Python 类型。

    DATE 列（analytic_kind == "datetime"）要求 asyncpg 绑定 datetime.date 对象。
    """
    kind = getattr(f, "analytic_kind", None)
    if kind == "datetime" and isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _build_where(
    filters: list[dict[str, Any]],
    field_map: dict[str, Any],
    db_type: str,
    filter_relation: str = "AND",
) -> tuple[str, dict[str, Any]]:
    """将 filters 列表构建为 WHERE SQL 和绑定参数。"""
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    for idx, item in enumerate(filters):
        fc = item.get("field", "")
        op = item.get("op", "eq")
        value = item.get("value")
        f = field_map.get(fc)
        col = _resolve_col_expr(f) if f else fc
        pkey = _safe_pkey("p", fc, idx)

        if op == "is_null":
            clauses.append(f"{col} IS NULL")
        elif op == "is_not_null":
            clauses.append(f"{col} IS NOT NULL")
        elif op == "between":
            vals = value if isinstance(value, list) else [value, value]
            clauses.append(f"{col} BETWEEN :{pkey}_0 AND :{pkey}_1")
            params[f"{pkey}_0"] = _coerce_param(vals[0], f)
            params[f"{pkey}_1"] = _coerce_param(vals[1], f)
        elif op == "in":
            vals = value if isinstance(value, list) else [value]
            pkeys = [f"{pkey}_{i}" for i in range(len(vals))]
            placeholders = ", ".join(f":{k}" for k in pkeys)
            clauses.append(f"{col} IN ({placeholders})")
            for k, v in zip(pkeys, vals):
                params[k] = _coerce_param(v, f)
        elif op == "like":
            like_val = value if (isinstance(value, str) and "%" in value) else f"%{value}%"
            clauses.append(f"{col} LIKE :{pkey}")
            params[pkey] = like_val
        else:
            op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            clauses.append(f"{col} {op_map.get(op, '=')} :{pkey}")
            params[pkey] = _coerce_param(value, f)

    relation = filter_relation.upper()
    return f" {relation} ".join(clauses), params


class QueryExecutor:
    """执行单对象 query_ontology 明细检索动作。

    协议（§3.2.2 字段编码版）：
    - select / filters.field / order_by.field 均接受 field_code
    - 不再接受字段中文名；传中文名时校验层报 UNSUPPORTED_FIELD
    - 支持 formula 字段（derived_metric / formula_metric / virtual_tag）展开
    - 内置参数校验（linked 字段、op 合法性、period_required）
    """

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
        """执行 query_ontology 明细查询。

        Args:
            object_code: 对象编码
            arguments:   符合 §3.2.2.1 协议的入参（field 均为 field_code）

        Returns:
            {"records": [...], "total": int, "meta": {"columns": [...], "object_code": ...}}
        """
        cls = self._loader.get_ontology_class(object_code)
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")

        alias = cls.datasource_alias or ""
        config = self._ds._configs.get(alias) if alias else None
        db_type = getattr(config, "db_type", "SQLITE") if config else "SQLITE"

        # ── 1. 构建字段映射（field_code → OntologyField） ─────────────────────
        field_map: dict[str, Any] = {f.field_code: f for f in cls.fields}

        # ── 2. 参数校验（直接用 field_code，无需翻译） ─────────────────────────
        required_groups = [
            f.required_filter_group for f in cls.fields if getattr(f, "required_filter_group", None)
        ]
        validator = VirtualActionValidator(list(field_map.values()))
        validator.validate_query(arguments, required_groups or None)

        # ── 3. 确定 SELECT 字段 ────────────────────────────────────────────────
        select_codes: list[str] = arguments.get("select") or []
        if select_codes:
            select_fields = [field_map[fc] for fc in select_codes if fc in field_map]
        else:
            select_fields = [
                f for f in cls.fields if getattr(f, "property_kind", "physical") != "linked"
            ]

        # ── 4. 构建 SQL ────────────────────────────────────────────────────────
        table = cls.table_name
        select_exprs = ", ".join(_resolve_select_expr(f, db_type) for f in select_fields)

        filter_relation = (arguments.get("filter_relation") or "AND").upper()
        where_sql, params = _build_where(
            arguments.get("filters") or [],
            field_map,
            db_type,
            filter_relation,
        )

        order_clauses: list[str] = []
        for ob in arguments.get("order_by") or []:
            fc = ob.get("field", "")
            direction = ob.get("direction", "asc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "ASC"
            f = field_map.get(fc)
            col = _resolve_col_expr(f) if f else fc
            order_clauses.append(f"{col} {direction}")

        limit = int(arguments.get("limit") or 100)
        offset = int(arguments.get("offset") or 0)

        sql = f"SELECT {select_exprs} FROM {_quote(table, db_type)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_clauses:
            sql += f" ORDER BY {', '.join(order_clauses)}"
        sql += f" LIMIT {limit} OFFSET {offset}"

        # ── 5. 执行 SQL ────────────────────────────────────────────────────────
        try:
            connector = self._ds.get_connector(alias)
            rows = await connector.execute(sql, params)
        except DataSourceUnavailableError:
            raise
        except Exception as exc:
            raise RuntimeError(f"query_ontology failed: {exc}") from exc

        # ── 6. 构建返回值 ──────────────────────────────────────────────────────
        col_keys = [f.field_code for f in select_fields]
        records = [
            dict(zip(col_keys, row)) if isinstance(row, (list, tuple)) else row for row in rows
        ]
        records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(
            records,
            select_fields,
        )

        columns = [
            {
                "name": f.field_code,
                "label": f.field_name,
                "type": (getattr(f, "field_type", "string") or "string").lower(),
            }
            for f in select_fields
        ]

        return {
            "records": records,
            "total": len(records),
            "meta": {"columns": columns, "object_code": object_code},
        }
