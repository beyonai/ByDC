"""ViewAnalyzeExecutor：执行视图级 analyze_* 虚拟动作（多表 JOIN 聚合统计）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from datacloud_data_sdk.executor.analyze_executor import (
    _agg_expr,
    _range_case_expr,
    _safe_pkey,
    _time_group_expr,
)
from datacloud_data_sdk.executor.view_executor_support import (
    build_filters_where,
    build_join_clauses,
    build_view_execution_context,
    build_view_result_columns_meta,
    collect_required_objects,
    quote_identifier,
)
from datacloud_data_sdk.executor.view_federation_support import (
    analyze_view_request,
    build_view_slice,
    object_source_alias,
)
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


class ViewAnalyzeExecutor:
    """执行视图级 analyze 虚拟动作（多对象 LEFT JOIN 分组统计）。"""

    def __init__(self, loader: OntologyLoader, ds_manager: DataSourceManager | None = None) -> None:
        self._loader = loader
        self._ds = ds_manager or DataSourceManager(
            getattr(loader._config, "datasource_configs", None) or {}
        )

    async def execute(self, view: Any, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行视图 analyze 查询，生成多对象 JOIN + GROUP BY + HAVING SQL。"""
        source_aliases = {
            object_source_alias(obj)
            for obj in getattr(view, "objects", []) or []
            if getattr(obj._cls, "source_type", "") == "DB"
        }
        plan = analyze_view_request(view, arguments, "compute")
        if len(plan.datasource_aliases) > 1:
            from datacloud_data_sdk.executor.view_federated_executor import (
                FederatedViewAnalyzeExecutor,
            )

            return await FederatedViewAnalyzeExecutor(self._loader, self._ds).execute(
                view,
                arguments,
                plan,
            )

        direct_view = view
        if len(source_aliases) > 1 and plan.closure_object_codes:
            direct_view = build_view_slice(view, plan.closure_object_codes)
        return await self._execute_direct(direct_view, arguments)

    async def _execute_direct(self, view: Any, arguments: dict[str, Any]) -> dict[str, Any]:
        """直接在单源数据源上执行视图 analyze。"""
        logger.info(
            "[ViewAnalyzeExecutor] execute called view=%s arguments_keys=%s"
            " dimensions=%s metrics=%s",
            getattr(view, "view_id", "?"),
            sorted(arguments.keys()),
            arguments.get("dimensions"),
            arguments.get("metrics"),
        )
        if not view.objects:
            return {"records": [], "total": 0, "meta": {"view_id": view.view_id}}

        context = build_view_execution_context(view, self._ds)
        alias = context.datasource_alias
        db_type = context.db_type
        field_to_alias_col = context.field_to_alias_col

        dimensions = arguments.get("dimensions") or []
        metrics = arguments.get("metrics") or []
        filters = arguments.get("filters") or []
        having_list = arguments.get("having") or []
        order_by = arguments.get("order_by") or []
        limit = int(arguments.get("limit") or 100)

        # SELECT + GROUP BY
        select_parts: list[str] = []
        group_by_parts: list[str] = []
        dim_aliases: dict[str, str] = {}
        col_keys: list[str] = []

        for dim in dimensions:
            fc = dim.get("field", "")
            group_op = dim.get("group_op", "self")
            buckets = dim.get("buckets")
            resolved = field_to_alias_col.get(fc)
            if not resolved:
                # 字段不在视图映射中：降级使用裸字段名（无表别名前缀）。
                # 比静默 continue 更安全：SQL 执行若失败会明确报错，而不是返回全量汇总误导调用方。
                logger.warning(
                    "[ViewAnalyzeExecutor] dimension field '%s' not in view mapping"
                    " (view=%s), falling back to bare column — check field_code",
                    fc,
                    getattr(view, "view_id", "?"),
                )
                col_expr = quote_identifier(fc, db_type)
            else:
                ta, col = resolved
                col_expr = f"{ta}.{quote_identifier(col, db_type)}"

            if group_op == "range" and buckets:
                alias_name = f"{fc}_range"
                dim_aliases[fc] = alias_name
                case_sql = _range_case_expr(
                    col_expr,
                    buckets,
                    quote_identifier(alias_name, db_type),
                )
                select_parts.append(case_sql)
                group_by_parts.append(
                    case_sql.split(f" AS {quote_identifier(alias_name, db_type)}")[0]
                )
                col_keys.append(alias_name)
            elif group_op in ("day", "month", "quarter", "year"):
                time_expr = _time_group_expr(col_expr, group_op, db_type)
                alias_name = f"{fc}_{group_op}"
                dim_aliases[fc] = alias_name
                select_parts.append(f"{time_expr} AS {quote_identifier(alias_name, db_type)}")
                group_by_parts.append(time_expr)
                col_keys.append(alias_name)
            else:
                dim_aliases[fc] = fc
                select_parts.append(f"{col_expr} AS {quote_identifier(fc, db_type)}")
                group_by_parts.append(col_expr)
                col_keys.append(fc)

        # Metrics
        metric_alias_to_expr: dict[str, str] = {}
        for mtr in metrics:
            agg = mtr.get("agg", "count")
            mtr_alias = mtr.get("as") or f"{agg}_result"
            if agg == "count_all":
                expr = "COUNT(*)"
            else:
                fc = mtr.get("field", "")
                resolved = field_to_alias_col.get(fc)
                if not resolved:
                    logger.warning(
                        "[ViewAnalyzeExecutor] metric field '%s' not in view mapping"
                        " (view=%s), falling back to bare column — check field_code",
                        fc,
                        getattr(view, "view_id", "?"),
                    )
                    expr = _agg_expr(agg, quote_identifier(fc, db_type))
                else:
                    ta, col = resolved
                    expr = _agg_expr(agg, f"{ta}.{quote_identifier(col, db_type)}")
            select_parts.append(f"{expr} AS {quote_identifier(mtr_alias, db_type)}")
            col_keys.append(mtr_alias)
            metric_alias_to_expr[mtr_alias] = expr

        # WHERE
        where_sql, params = build_filters_where(
            filters,
            field_to_alias_col,
            db_type,
            _safe_pkey,
            str(arguments.get("filter_relation") or "AND"),
        )

        # HAVING
        having_clauses: list[str] = []
        for idx, hav in enumerate(having_list):
            hfield = hav.get("field", "")
            hop = hav.get("op", "gt")
            hval = hav.get("value")
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

        # ORDER BY
        order_clauses: list[str] = []
        for ob in order_by:
            ob_field = ob.get("field", "")
            direction = ob.get("direction", "desc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "DESC"
            if ob_field in metric_alias_to_expr:
                order_clauses.append(f"{metric_alias_to_expr[ob_field]} {direction}")
            else:
                resolved = field_to_alias_col.get(ob_field)
                if resolved:
                    ta, col = resolved
                    order_clauses.append(f"{ta}.{quote_identifier(col, db_type)} {direction}")

        required_fields = {item.get("field", "") for item in dimensions}
        required_fields.update(
            metric.get("field", "") for metric in metrics if metric.get("agg") != "count_all"
        )
        required_fields.update(item.get("field", "") for item in filters)
        required_fields.update(
            item.get("field", "")
            for item in order_by
            if item.get("field", "") not in metric_alias_to_expr
        )
        required_fields.discard("")

        # JOIN
        join_clauses = build_join_clauses(
            view,
            db_type,
            collect_required_objects(view, context.field_to_object_code, required_fields),
        )
        from_clause = f"{quote_identifier(context.anchor_table, db_type)} t0"
        if join_clauses:
            from_clause += " " + " ".join(join_clauses)

        select_sql = ", ".join(select_parts) or "COUNT(*) AS total_count"
        sql = f"SELECT {select_sql} FROM {from_clause}"
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
        except Exception as exc:
            raise RuntimeError(f"view analyze query failed: {exc}") from exc

        records = [
            dict(zip(col_keys, row, strict=False)) if isinstance(row, (list, tuple)) else row
            for row in rows
        ]
        columns_meta = build_view_result_columns_meta(view, col_keys, loader=self._loader)
        return {
            "records": records,
            "total": len(records),
            "meta": {"view_id": view.view_id, "columns": columns_meta},
        }
