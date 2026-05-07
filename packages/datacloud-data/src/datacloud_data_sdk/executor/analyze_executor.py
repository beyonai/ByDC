"""AnalyzeExecutor：执行 analyze_* 虚拟动作（单对象分组统计）。

协议格式（新）：
{
  "dimensions": [
    {"field": "period", "group_op": "month"},
    {"field": "age", "group_op": "range", "buckets": [{"from": 0, "to": 18, "label": "未成年"}, ...]}
  ],
  "metrics": [
    {"field": "revenue", "agg": "sum", "as": "营收汇总"},
    {"agg": "count_all", "as": "记录数"}
  ],
  "filters": [{"field": "period", "op": "between", "value": ["2026-01", "2026-03"]}],
  "having": [{"field": "营收汇总", "op": "gt", "value": 100000}],
  "order_by": [{"field": "营收汇总", "direction": "desc"}],
  "limit": 100
}
"""

from __future__ import annotations

import re
from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

_PKEY_RE = re.compile(r"[^a-zA-Z0-9]")


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


# ── 逻辑函数 → 方言 SQL 翻译 ──────────────────────────────────────────────────


def _time_group_expr(col_expr: str, group_op: str, db_type: str) -> str:
    """
    将 group_op=day/month/quarter/year 翻译为对应数据库的时间分组表达式。
    """
    dt = db_type.upper()
    if group_op == "day":
        if dt in ("MYSQL",):
            return f"DATE({col_expr})"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"DATE_TRUNC('day', {col_expr})::date"
        if dt == "CLICKHOUSE":
            return f"toDate({col_expr})"
        return f"DATE({col_expr})"  # SQLite/fallback

    if group_op == "month":
        if dt in ("MYSQL",):
            return f"DATE_FORMAT({col_expr}, '%Y-%m')"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"TO_CHAR(DATE_TRUNC('month', {col_expr}), 'YYYY-MM')"
        if dt == "CLICKHOUSE":
            return f"toStartOfMonth({col_expr})"
        # SQLite
        return f"strftime('%Y-%m', {col_expr})"

    if group_op == "quarter":
        if dt in ("MYSQL",):
            return f"CONCAT(YEAR({col_expr}), '-Q', QUARTER({col_expr}))"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"CONCAT(DATE_PART('year', {col_expr})::int, '-Q', DATE_PART('quarter', {col_expr})::int)"
        if dt == "CLICKHOUSE":
            return f"toStartOfQuarter({col_expr})"
        # SQLite
        return f"CAST(strftime('%Y', {col_expr}) AS TEXT) || '-Q' || CAST((CAST(strftime('%m', {col_expr}) AS INTEGER) + 2) / 3 AS TEXT)"

    if group_op == "year":
        if dt in ("MYSQL",):
            return f"YEAR({col_expr})"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"DATE_PART('year', {col_expr})::int"
        if dt == "CLICKHOUSE":
            return f"toYear({col_expr})"
        return f"strftime('%Y', {col_expr})"

    # self → 直接返回列表达式
    return col_expr


def _range_case_expr(col_expr: str, buckets: list[dict[str, Any]], alias: str) -> str:
    """
    将 range 分桶翻译为 CASE WHEN ... END AS alias 表达式。
    """
    parts: list[str] = []
    for bucket in buckets:
        frm = bucket.get("from")
        to = bucket.get("to")
        label = bucket.get("label", "其他")
        conditions: list[str] = []
        if frm is not None:
            conditions.append(f"{col_expr} >= {frm}")
        if to is not None:
            conditions.append(f"{col_expr} < {to}")
        if conditions:
            parts.append(f"WHEN {' AND '.join(conditions)} THEN '{label}'")
        else:
            parts.append(f"ELSE '{label}'")
    case_sql = "CASE " + " ".join(parts) + " ELSE '其他' END"
    return f"{case_sql} AS {alias}"


def _agg_expr(agg: str, col_expr: str) -> str:
    """将聚合函数名翻译为 SQL 表达式。"""
    agg = agg.lower()
    if agg == "count":
        return f"COUNT({col_expr})"
    if agg == "count_distinct":
        return f"COUNT(DISTINCT {col_expr})"
    if agg == "count_all":
        return "COUNT(*)"
    if agg == "sum":
        return f"SUM({col_expr})"
    if agg == "avg":
        return f"AVG({col_expr})"
    if agg == "min":
        return f"MIN({col_expr})"
    if agg == "max":
        return f"MAX({col_expr})"
    return f"{agg.upper()}({col_expr})"


def _build_filters_where(
    filters: list[dict[str, Any]],
    field_to_col: dict[str, str],
    db_type: str,
) -> tuple[str, dict[str, Any]]:
    """构建 WHERE 子句（与 lookup_executor 相同逻辑）。"""
    if not filters:
        return "", {}
    q = lambda x: _quote(x, db_type)
    clauses: list[str] = []
    params: dict[str, Any] = {}

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
            like_val = value if (isinstance(value, str) and "%" in value) else f"%{value}%"
            clauses.append(f"{q(col)} LIKE :{pkey}")
            params[pkey] = like_val
        else:
            op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            clauses.append(f"{q(col)} {op_map.get(op, '=')} :{pkey}")
            params[pkey] = value

    return " AND ".join(clauses), params


class AnalyzeExecutor:
    """执行单对象 analyze 虚拟动作（分组统计 SQL）。"""

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
        """执行 analyze 动作，返回 {"records": [...], "total": int, "meta": {...}}。"""
        cls = self._loader.get_ontology_class(object_code)
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")

        alias = cls.datasource_alias or ""
        config = self._ds._configs.get(alias) if alias else None
        db_type = getattr(config, "db_type", "SQLITE") if config else "SQLITE"
        q = lambda x: _quote(x, db_type)

        # 物理字段映射
        physical_fields = [
            f
            for f in cls.fields
            if getattr(f, "property_kind", "physical") not in ("derived", "linked")
        ]
        field_to_col: dict[str, str] = {}
        for f in physical_fields:
            if f.source_column:
                field_to_col[f.field_code] = f.source_column
            else:
                field_to_col[f.field_code] = f.field_code
        field_map = {f.field_code: f for f in cls.fields}
        table = cls.table_name

        dimensions = arguments.get("dimensions") or []
        dimensions = [
            {"field": d} if isinstance(d, str) else d for d in dimensions
        ]  # 兼容字符串元素
        metrics = arguments.get("metrics") or []
        filters = arguments.get("filters") or []
        having_list = arguments.get("having") or []
        order_by = arguments.get("order_by") or []
        limit = int(arguments.get("limit") or 100)

        # ── SELECT 子句构建 ────────────────────────────────────────────────────
        select_parts: list[str] = []
        group_by_parts: list[str] = []
        dim_aliases: dict[str, str] = {}  # field_code → select alias

        for dim in dimensions:
            fc = dim.get("field", "")
            group_op = dim.get("group_op", "self")
            buckets = dim.get("buckets")
            col = field_to_col.get(fc, fc)
            col_expr = f"{q(table)}.{q(col)}"

            if group_op == "range" and buckets:
                col_alias = f"{fc}_range"
                dim_aliases[fc] = col_alias
                case_expr = _range_case_expr(col_expr, buckets, q(col_alias))
                select_parts.append(case_expr)
                # CASE WHEN 不直接放入 GROUP BY，需要重新写
                group_by_parts.append(case_expr.split(f" AS {q(col_alias)}")[0])
            elif group_op in ("day", "month", "quarter", "year"):
                time_expr = _time_group_expr(col_expr, group_op, db_type)
                col_alias = f"{fc}_{group_op}"
                dim_aliases[fc] = col_alias
                select_parts.append(f"{time_expr} AS {q(col_alias)}")
                group_by_parts.append(time_expr)
            else:
                # self → 直接使用列
                col_alias = fc
                dim_aliases[fc] = fc
                select_parts.append(f"{col_expr} AS {q(fc)}")
                group_by_parts.append(col_expr)

        # metrics
        metric_alias_to_expr: dict[str, str] = {}  # 用于 HAVING 替换
        col_keys: list[str] = [
            dim_aliases.get(dim.get("field", ""), dim.get("field", "")) for dim in dimensions
        ]

        for mtr in metrics:
            agg = mtr.get("agg", "count")
            col_alias = mtr.get("as") or f"{agg}_result"
            if agg == "count_all":
                expr = "COUNT(*)"
            else:
                fc = mtr.get("field", "")
                col = field_to_col.get(fc, fc)
                col_expr = f"{q(table)}.{q(col)}"
                expr = _agg_expr(agg, col_expr)
            select_parts.append(f"{expr} AS {q(col_alias)}")
            col_keys.append(col_alias)
            metric_alias_to_expr[col_alias] = expr

        # ── WHERE ─────────────────────────────────────────────────────────────
        where_sql, params = _build_filters_where(filters, field_to_col, db_type)

        # ── HAVING ────────────────────────────────────────────────────────────
        having_clauses: list[str] = []
        for idx, hav in enumerate(having_list):
            hfield = hav.get("field", "")
            hop = hav.get("op", "gt")
            hval = hav.get("value")
            # hfield 必须是 metrics.as 别名 → 替换为原始聚合表达式
            expr = metric_alias_to_expr.get(hfield, hfield)
            pkey = _safe_pkey("h", hfield, idx)
            if hop == "between":
                vals = hval if isinstance(hval, list) else [hval, hval]
                having_clauses.append(f"{expr} BETWEEN :{pkey}_0 AND :{pkey}_1")
                params[f"{pkey}_0"] = vals[0]
                params[f"{pkey}_1"] = vals[1]
            else:
                op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
                having_clauses.append(f"{expr} {op_map.get(hop, '>')} :{pkey}")
                params[pkey] = hval

        # ── ORDER BY ──────────────────────────────────────────────────────────
        order_clauses: list[str] = []
        for ob in order_by:
            ob_field = ob.get("field", "")
            direction = ob.get("direction", "desc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "DESC"
            # ob_field 可以是 metrics.as 别名或维度字段
            if ob_field in metric_alias_to_expr:
                order_clauses.append(f"{metric_alias_to_expr[ob_field]} {direction}")
            elif ob_field in dim_aliases:
                order_clauses.append(f"{q(dim_aliases[ob_field])} {direction}")
            else:
                order_clauses.append(f"{q(ob_field)} {direction}")

        # ── 拼接完整 SQL ──────────────────────────────────────────────────────
        select_sql = ", ".join(select_parts) or "COUNT(*) AS total_count"
        sql = f"SELECT {select_sql} FROM {q(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if group_by_parts:
            sql += f" GROUP BY {', '.join(group_by_parts)}"
        if having_clauses:
            sql += f" HAVING {' AND '.join(having_clauses)}"
        if order_clauses:
            sql += f" ORDER BY {', '.join(order_clauses)}"
        sql += f" LIMIT {limit}"

        try:
            connector = self._ds.get_connector(alias)
            rows = await connector.execute(sql, params)
        except DataSourceUnavailableError:
            raise
        except Exception as exc:
            raise RuntimeError(f"analyze query failed: {exc}") from exc

        records = [
            dict(zip(col_keys, row)) if isinstance(row, (list, tuple)) else row for row in rows
        ]

        # meta.columns
        columns: list[dict[str, str]] = []
        for dim in dimensions:
            fc = dim.get("field", "")
            col_alias = dim_aliases.get(fc, fc)
            f = field_map.get(fc)
            columns.append(
                {
                    "name": col_alias,
                    "label": getattr(f, "field_name", col_alias) if f else col_alias,
                    "type": "string",
                }
            )
        for mtr in metrics:
            col_alias = mtr.get("as") or f"{mtr.get('agg', 'count')}_result"
            columns.append({"name": col_alias, "label": col_alias, "type": "number"})

        return {
            "records": records,
            "total": len(records),
            "meta": {"columns": columns, "object_code": object_code},
        }
