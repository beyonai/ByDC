"""ComputeExecutor：执行 compute_ontology 虚拟动作（单对象分组统计）。

协议格式（§3.2.3）：
{
  "dimensions": [
    {"field": "字段中文名", "group_op": "month|self|range|...", "buckets": [...]},
  ],
  "metrics": [
    {"field": "字段中文名", "agg": "sum|avg|min|max|count|count_distinct", "as": "alias"},
    {"agg": "count_all", "as": "alias"}
  ],
  "filters":  [{"field": "中文名", "op": "...", "value": ...}],
  "having":   [{"field": "metrics.as 别名", "op": "...", "value": ...}],
  "order_by": [{"field": "metrics.as 别名 或维度alias", "direction": "asc|desc"}],
  "limit":    100
}

与 AnalyzeExecutor 的区别：
- field 使用字段中文名（field_name），内部通过 name_to_code 反向映射为 field_code
- 支持 derived_metric / formula_metric / virtual_tag 的 formula 展开
- period analytic_kind 字段用 substr 提取月份/年份（已是 YYYY-MM 格式）
- snapshot_metric 跨账期 SUM 前置检测
- 校验前置：validate_analyze（字段合法性、group_op、agg op、having 别名、period_required）
"""

from __future__ import annotations

import re
from typing import Any

from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.virtual_action.validator import (
    VirtualActionValidationError,
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


def _time_group_expr(col_expr: str, group_op: str, db_type: str) -> str:
    """将 group_op=day/month/quarter/year 翻译为对应数据库的时间分组表达式。"""
    dt = db_type.upper()
    if group_op == "day":
        if dt == "MYSQL":
            return f"DATE({col_expr})"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"DATE_TRUNC('day', {col_expr})::date"
        if dt == "CLICKHOUSE":
            return f"toDate({col_expr})"
        return f"DATE({col_expr})"

    if group_op == "month":
        if dt == "MYSQL":
            return f"DATE_FORMAT({col_expr}, '%Y-%m')"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"TO_CHAR(DATE_TRUNC('month', {col_expr}), 'YYYY-MM')"
        if dt == "CLICKHOUSE":
            return f"toStartOfMonth({col_expr})"
        return f"strftime('%Y-%m', {col_expr})"

    if group_op == "quarter":
        if dt == "MYSQL":
            return f"CONCAT(YEAR({col_expr}), '-Q', QUARTER({col_expr}))"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"CONCAT(DATE_PART('year', {col_expr})::int, '-Q', DATE_PART('quarter', {col_expr})::int)"
        if dt == "CLICKHOUSE":
            return f"toStartOfQuarter({col_expr})"
        return (
            f"CAST(strftime('%Y', {col_expr}) AS TEXT) || '-Q' || "
            f"CAST((CAST(strftime('%m', {col_expr}) AS INTEGER) + 2) / 3 AS TEXT)"
        )

    if group_op == "year":
        if dt == "MYSQL":
            return f"YEAR({col_expr})"
        if dt in ("POSTGRESQL", "OPENGAUSS"):
            return f"DATE_PART('year', {col_expr})::int"
        if dt == "CLICKHOUSE":
            return f"toYear({col_expr})"
        return f"strftime('%Y', {col_expr})"

    return col_expr


def _period_group_expr(col_expr: str, group_op: str) -> str:
    """period analytic_kind 字段的分组表达式。

    period 字段存储格式为 'YYYY-MM'，无需 strftime 转换。
    - month:   取前 7 位 → 'YYYY-MM'
    - year:    取前 4 位 → 'YYYY'
    - quarter: 从月份计算季度 → 'YYYY-Q#'
    """
    if group_op == "month":
        return f"substr({col_expr}, 1, 7)"
    if group_op == "year":
        return f"substr({col_expr}, 1, 4)"
    if group_op == "quarter":
        return (
            f"substr({col_expr}, 1, 4) || '-Q' || "
            f"CAST((CAST(substr({col_expr}, 6, 2) AS INTEGER) + 2) / 3 AS TEXT)"
        )
    return col_expr  # self


def _range_case_expr(col_expr: str, buckets: list[dict[str, Any]], alias: str) -> str:
    """将 range 分桶翻译为 CASE WHEN ... END AS alias 表达式。"""
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
    field_map: dict[str, Any],
    db_type: str,
    filter_relation: str = "AND",
) -> tuple[str, dict[str, Any]]:
    """构建 WHERE 子句，支持 formula 字段的列表达式解析。"""
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    for idx, item in enumerate(filters):
        fc = item.get("field", "")
        op = item.get("op", "eq")
        value = item.get("value")

        f = field_map.get(fc)
        col = _resolve_col_expr(f, fc)
        pkey = _safe_pkey("p", fc, idx)

        if op == "is_null":
            clauses.append(f"{col} IS NULL")
        elif op == "is_not_null":
            clauses.append(f"{col} IS NOT NULL")
        elif op == "between":
            vals = value if isinstance(value, list) else [value, value]
            clauses.append(f"{col} BETWEEN :{pkey}_0 AND :{pkey}_1")
            params[f"{pkey}_0"] = vals[0]
            params[f"{pkey}_1"] = vals[1]
        elif op == "in":
            vals = value if isinstance(value, list) else [value]
            pkeys = [f"{pkey}_{i}" for i in range(len(vals))]
            placeholders = ", ".join(f":{k}" for k in pkeys)
            clauses.append(f"{col} IN ({placeholders})")
            for k, v in zip(pkeys, vals):
                params[k] = v
        elif op == "like":
            like_val = value if (isinstance(value, str) and "%" in value) else f"%{value}%"
            clauses.append(f"{col} LIKE :{pkey}")
            params[pkey] = like_val
        else:
            op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            clauses.append(f"{col} {op_map.get(op, '=')} :{pkey}")
            params[pkey] = value

    relation = filter_relation.upper()
    return f" {relation} ".join(clauses), params


def _resolve_col_expr(f: Any | None, fc: str) -> str:
    """WHERE / ORDER BY 中的字段列表达式（不含别名）。"""
    if f is None:
        return fc
    formula = getattr(f, "formula", None)
    kind = getattr(f, "analytic_kind", None)
    if formula and kind in _FORMULA_KINDS:
        return f"({formula})"
    col = getattr(f, "source_column", None) or fc
    return col


def _translate_arguments(
    arguments: dict[str, Any],
    name_to_code: dict[str, str],
) -> dict[str, Any]:
    """将 arguments 中字段中文名替换为 field_code。

    翻译 dimensions[i].field、metrics[i].field、filters[i].field。
    having[i].field 和 order_by[i].field 是别名，不翻译。
    """
    translated: dict[str, Any] = dict(arguments)

    if "dimensions" in arguments:
        new_dims = []
        for dim in arguments["dimensions"] or []:
            new_dim = dict(dim)
            fname = dim.get("field", "")
            new_dim["field"] = name_to_code.get(fname, fname)
            new_dims.append(new_dim)
        translated["dimensions"] = new_dims

    if "metrics" in arguments:
        new_metrics = []
        for mtr in arguments["metrics"] or []:
            new_mtr = dict(mtr)
            if "field" in mtr:
                fname = mtr.get("field", "")
                new_mtr["field"] = name_to_code.get(fname, fname)
            new_metrics.append(new_mtr)
        translated["metrics"] = new_metrics

    if "filters" in arguments:
        new_filters = []
        for item in arguments["filters"] or []:
            new_item = dict(item)
            fname = item.get("field", "")
            new_item["field"] = name_to_code.get(fname, fname)
            new_filters.append(new_item)
        translated["filters"] = new_filters

    return translated


def _check_snapshot_cross_period_sum(
    translated: dict[str, Any],
    field_map: dict[str, Any],
) -> None:
    """检测 snapshot_metric 跨账期 SUM 禁止规则。

    若满足以下两个条件则报错：
    1. metrics 中存在 agg=sum 且字段为 snapshot_metric
    2. dimensions 中存在 analytic_kind=period 的字段（跨账期分组）
    """
    dimensions = translated.get("dimensions") or []
    metrics = translated.get("metrics") or []

    # 检查 dimensions 中是否有 period 字段
    has_period_dim = any(
        getattr(field_map.get(dim.get("field", "")), "analytic_kind", None) == "period"
        for dim in dimensions
    )
    if not has_period_dim:
        return

    # 检查 metrics 中是否有 snapshot_metric + sum
    for mtr in metrics:
        if mtr.get("agg", "").lower() != "sum":
            continue
        fc = mtr.get("field", "")
        f = field_map.get(fc)
        if f and getattr(f, "analytic_kind", None) == "snapshot_metric":
            fname = getattr(f, "field_name", fc)
            raise VirtualActionValidationError(
                f"拍照指标 '{fname}' 不支持跨账期 SUM，"
                "请改用 MAX/MIN，或在 filters 中锁定账期后按其他维度统计",
                "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
            )


class ComputeExecutor:
    """执行单对象 compute_ontology 分组统计动作。

    与 AnalyzeExecutor 的区别：
    - 接受字段中文名（field_name），内部映射到 field_code
    - 支持 formula 字段（derived_metric / formula_metric / virtual_tag）展开
    - period 字段（YYYY-MM 格式）使用 substr 进行时间分组，无需 strftime
    - 内置 snapshot_metric 跨账期 SUM 前置检测
    - 调用 validate_analyze 校验 metrics/dimensions/having/period_required
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
        """执行 compute_ontology 分组统计查询。

        Args:
            object_code: 对象编码
            arguments:   符合 §3.2.3 协议的入参（字段名为中文名）

        Returns:
            {"records": [...], "total": int, "meta": {"columns": [...], "object_code": ...}}
        """
        cls = self._loader.get_ontology_class(object_code)
        if not cls.table_name:
            raise ValueError(f"Object {object_code} missing table_name")

        alias = cls.datasource_alias or ""
        config = self._ds._configs.get(alias) if alias else None
        db_type = getattr(config, "db_type", "SQLITE") if config else "SQLITE"

        # ── 1. 构建映射 ───────────────────────────────────────────────────────
        field_map: dict[str, Any] = {f.field_code: f for f in cls.fields}
        name_to_code: dict[str, str] = {f.field_name: f.field_code for f in cls.fields}

        # ── 2. 把入参中的中文名翻译成 field_code ──────────────────────────────
        translated = _translate_arguments(arguments, name_to_code)

        # ── 3. snapshot_metric 跨账期 SUM 前置检测 ────────────────────────────
        _check_snapshot_cross_period_sum(translated, field_map)

        # ── 4. 参数校验（validate_analyze） ───────────────────────────────────
        required_groups = [
            f.required_filter_group
            for f in cls.fields
            if getattr(f, "required_filter_group", None)
        ]
        # filter_relation=OR + period_required 冲突检测（与 query_ 语义相同）
        filter_relation = (arguments.get("filter_relation") or "AND").upper()
        if filter_relation == "OR" and required_groups and "period_required" in required_groups:
            raise VirtualActionValidationError(
                "该对象含账期强制约束，不允许使用 filter_relation=OR，"
                "OR 连接会使账期条件失去强制约束效果",
                "VIRTUAL_ACTION_ERR_INVALID",
            )
        validator = VirtualActionValidator(list(field_map.values()))
        validator.validate_analyze(translated, required_groups or None)

        # ── 5. 构建 SQL ────────────────────────────────────────────────────────
        table = cls.table_name
        dimensions = translated.get("dimensions") or []
        metrics = translated.get("metrics") or []
        filters = translated.get("filters") or []
        having_list = translated.get("having") or []
        order_by = translated.get("order_by") or []
        limit = int(arguments.get("limit") or 100)

        select_parts: list[str] = []
        group_by_parts: list[str] = []
        dim_aliases: dict[str, str] = {}  # field_code → select alias

        for dim in dimensions:
            fc = dim.get("field", "")
            group_op = dim.get("group_op", "self")
            buckets = dim.get("buckets")
            f = field_map.get(fc)
            col = _resolve_col_expr(f, fc)
            analytic_kind = getattr(f, "analytic_kind", None) if f else None

            if group_op == "range" and buckets:
                col_alias = f"{fc}_range"
                dim_aliases[fc] = col_alias
                q_alias = _quote(col_alias, db_type)
                case_expr = _range_case_expr(col, buckets, q_alias)
                select_parts.append(case_expr)
                # GROUP BY 重新写 CASE 表达式（不含 AS 部分）
                group_by_parts.append(case_expr.split(f" AS {q_alias}")[0])
            elif group_op in ("day", "month", "quarter", "year"):
                col_alias = f"{fc}_{group_op}"
                dim_aliases[fc] = col_alias
                q_alias = _quote(col_alias, db_type)
                # period 字段：存储格式已为 YYYY-MM，直接用 substr
                if analytic_kind == "period":
                    group_expr = _period_group_expr(_quote(col, db_type), group_op)
                else:
                    group_expr = _time_group_expr(_quote(col, db_type), group_op, db_type)
                select_parts.append(f"{group_expr} AS {q_alias}")
                group_by_parts.append(group_expr)
            else:
                # self → 直接使用列
                col_alias = fc
                dim_aliases[fc] = fc
                q_col = _quote(col, db_type)
                q_alias = _quote(fc, db_type)
                select_parts.append(f"{q_col} AS {q_alias}")
                group_by_parts.append(q_col)

        # metrics
        metric_alias_to_expr: dict[str, str] = {}
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
                f = field_map.get(fc)
                formula = getattr(f, "formula", None) if f else None
                kind = getattr(f, "analytic_kind", None) if f else None
                if formula and kind in _FORMULA_KINDS:
                    col_expr = f"({formula})"
                else:
                    col = _resolve_col_expr(f, fc)
                    col_expr = _quote(col, db_type)
                expr = _agg_expr(agg, col_expr)
            select_parts.append(f"{expr} AS {_quote(col_alias, db_type)}")
            col_keys.append(col_alias)
            metric_alias_to_expr[col_alias] = expr

        # ── WHERE ─────────────────────────────────────────────────────────────
        where_sql, params = _build_filters_where(filters, field_map, db_type, filter_relation)

        # ── HAVING ────────────────────────────────────────────────────────────
        having_clauses: list[str] = []
        for idx, hav in enumerate(having_list):
            hfield = hav.get("field", "")
            hop = hav.get("op", "gt")
            hval = hav.get("value")
            expr = metric_alias_to_expr.get(hfield, _quote(hfield, db_type))
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
            if ob_field in metric_alias_to_expr:
                order_clauses.append(f"{metric_alias_to_expr[ob_field]} {direction}")
            elif ob_field in dim_aliases:
                order_clauses.append(f"{_quote(dim_aliases[ob_field], db_type)} {direction}")
            else:
                order_clauses.append(f"{_quote(ob_field, db_type)} {direction}")

        # ── 拼接完整 SQL ──────────────────────────────────────────────────────
        select_sql = ", ".join(select_parts) or "COUNT(*) AS total_count"
        sql = f"SELECT {select_sql} FROM {_quote(table, db_type)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if group_by_parts:
            sql += f" GROUP BY {', '.join(group_by_parts)}"
        if having_clauses:
            sql += f" HAVING {' AND '.join(having_clauses)}"
        if order_clauses:
            sql += f" ORDER BY {', '.join(order_clauses)}"
        sql += f" LIMIT {limit}"

        # ── 6. 执行 SQL ────────────────────────────────────────────────────────
        try:
            connector = self._ds.get_connector(alias)
            rows = await connector.execute(sql, params)
        except DataSourceUnavailableError:
            raise
        except Exception as exc:
            raise RuntimeError(f"compute_ontology failed: {exc}") from exc

        # ── 7. 构建返回值 ──────────────────────────────────────────────────────
        records = [
            dict(zip(col_keys, row)) if isinstance(row, (list, tuple)) else row
            for row in rows
        ]

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
