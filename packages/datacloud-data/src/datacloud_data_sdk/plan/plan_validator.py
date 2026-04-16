"""PlanValidator: 校验 QueryExecutionPlan 合法性。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from datacloud_data_sdk.plan.models import (
    ObjectViewPayload,
    PlanStep,
    QueryExecutionPlan,
)

_SUPPORTED_DB_TYPES = {"POSTGRESQL", "MYSQL", "OPENGAUSS", "SQLITE", "CLICKHOUSE"}

_SQL_KEYWORDS = {
    "select",
    "from",
    "where",
    "join",
    "on",
    "and",
    "or",
    "not",
    "in",
    "between",
    "like",
    "ilike",
    "is",
    "null",
    "as",
    "order",
    "by",
    "group",
    "having",
    "limit",
    "offset",
    "distinct",
    "all",
    "union",
    "intersect",
    "except",
    "exists",
    "case",
    "when",
    "then",
    "else",
    "end",
    "asc",
    "desc",
    "inner",
    "left",
    "right",
    "outer",
    "cross",
    "full",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "into",
    "values",
    "set",
    "table",
    "index",
    "view",
    "true",
    "false",
    "with",
    "interval",
    "over",
    "partition",
    "range",
    "rows",
    "unbounded",
    "preceding",
    "following",
    "default",
}

# PostgreSQL ::type 及 CAST(x AS type) 中的类型名，避免被误判为未知列
_SQL_TYPES = {
    "decimal",
    "numeric",
    "integer",
    "int",
    "bigint",
    "smallint",
    "real",
    "double",
    "float",
    "boolean",
    "bool",
    "text",
    "varchar",
    "char",
    "timestamp",
    "timestamptz",
    "date",
    "time",
    "interval",
    "json",
    "jsonb",
    "uuid",
    "bytea",
    "serial",
    "bigserial",
}

_SQL_FUNCTIONS = {
    # 聚合
    "count",
    "sum",
    "avg",
    "max",
    "min",
    "group_concat",
    "string_agg",
    "array_agg",
    "json_agg",
    "json_build_object",
    # 空值/类型
    "coalesce",
    "ifnull",
    "nullif",
    "cast",
    "convert",
    # 字符串
    "upper",
    "lower",
    "trim",
    "ltrim",
    "rtrim",
    "length",
    "char_length",
    "substr",
    "substring",
    "concat",
    "concat_ws",
    "replace",
    "position",
    "strpos",
    "split_part",
    "left",
    "right",
    "lpad",
    "rpad",
    "regexp_replace",
    "regexp_match",
    "repeat",
    # 数值
    "round",
    "abs",
    "ceil",
    "floor",
    "mod",
    "power",
    "sqrt",
    "random",
    "greatest",
    "least",
    # 日期时间 - 标准/PostgreSQL/OpenGauss/MySQL
    "now",
    "current_date",
    "current_time",
    "current_timestamp",
    "localtime",
    "localtimestamp",
    "date",
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "extract",
    "date_trunc",
    "age",
    "make_date",
    "make_interval",
    "to_char",
    "to_date",
    "to_timestamp",
    "date_part",
    "date_format",
    "str_to_date",
    "date_add",
    "date_sub",
    # 条件
    "iif",
    # 窗口
    "row_number",
    "rank",
    "dense_rank",
    "lag",
    "lead",
    "first_value",
    "last_value",
    "ntile",
    # 其他
    "unnest",
    "generate_series",
}

_IDENTIFIER_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
_ALIAS_AS_RE = re.compile(r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE)
_TABLE_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)
# 从 FROM/JOIN 提取表名（不含子查询），用于无 sqlglot 时的跨源校验
_TABLE_FROM_JOIN_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?!\s*\()(?:\w+\.)?(\w+)",
    re.IGNORECASE,
)

try:  # 运行环境未安装 sqlglot 时自动降级为纯 token 校验
    import sqlglot  # type: ignore[import]
    from sqlglot.optimizer.scope import build_scope  # type: ignore[import]
except Exception:  # pragma: no cover
    sqlglot = None
    build_scope = None


class SqlValidationError(TypedDict, total=False):
    code: str
    message: str
    detail: dict[str, Any] | None


SqlDialectValidator = Callable[
    [str, ObjectViewPayload, PlanStep],
    list[SqlValidationError],
]


def _generic_sql_token_validate(
    sql: str,
    payload: ObjectViewPayload,
    step: PlanStep,
) -> list[SqlValidationError]:
    """基于 token 的通用 SQL 校验：字段/表/别名/函数/类型是否可识别。"""
    if not sql:
        return []

    # 无 sqlglot 时也做跨源校验：用正则提取表名
    tables_in_query = _extract_tables_from_sql_regex(sql)
    cross_errors = _validate_cross_source_join_from_tables(tables_in_query, payload, step)
    if cross_errors:
        return cross_errors

    cleaned = re.sub(r"'[^']*'", "", sql)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", "", cleaned)

    tokens = set(_IDENTIFIER_RE.findall(cleaned))

    known: set[str] = set()
    for obj in payload.objects:
        if obj.table:
            known.add(obj.table.lower())
        for f in obj.fields:
            # SQL 中引用列必须使用 source_column；有 source_column 时禁止使用 name
            col_name = (f.source_column or f.name).lower()
            known.add(col_name)

    aliases: set[str] = set()
    for m in _ALIAS_AS_RE.finditer(cleaned):
        aliases.add(m.group(1).lower())
    for m in _TABLE_ALIAS_RE.finditer(cleaned):
        candidate = m.group(2).lower()
        if candidate not in _SQL_KEYWORDS:
            aliases.add(candidate)

    valid = _SQL_KEYWORDS | _SQL_FUNCTIONS | _SQL_TYPES | known | aliases

    errors: list[SqlValidationError] = []
    for token in sorted(tokens):
        if token.lower() not in valid:
            errors.append(
                {
                    "code": "UNKNOWN_COLUMN",
                    "message": f"SQL references unknown column {token!r}",
                    "detail": {"identifier": token, "step_id": step.step_id},
                }
            )
    return errors


def _extract_tables_from_sql_regex(sql: str) -> set[str]:
    """从 SQL 中通过正则提取 FROM/JOIN 后的表名（不含子查询），用于无 sqlglot 时的跨源校验。"""
    tables: set[str] = set()
    for m in _TABLE_FROM_JOIN_RE.finditer(sql):
        name = m.group(1).lower()
        if name and name not in _SQL_KEYWORDS:
            tables.add(name)
    return tables


def _validate_cross_source_join_from_tables(
    tables_in_query: set[str],
    payload: ObjectViewPayload,
    step: PlanStep,
) -> list[SqlValidationError]:
    """校验多表是否来自同一数据源，禁止跨源 JOIN。"""
    if len(tables_in_query) <= 1:
        return []

    source_by_id: dict[str, Any] = {s.source_id: s for s in payload.sources}
    table_to_datasource: dict[str, str] = {}
    for obj in payload.objects:
        if not obj.table:
            continue
        source = source_by_id.get(obj.source_id)
        if source is None or source.source_type != "DB":
            continue
        if source.datasource_alias:
            table_to_datasource[obj.table.lower()] = source.datasource_alias

    table_datasources: list[tuple[str, str]] = []
    for t in tables_in_query:
        if t in table_to_datasource:
            table_datasources.append((t, table_to_datasource[t]))

    datasources_used = {ds for _, ds in table_datasources}
    if len(datasources_used) <= 1:
        return []

    msg_parts = ", ".join(f"{t} ({ds})" for t, ds in sorted(table_datasources))
    return [
        {
            "code": "CROSS_SOURCE_JOIN",
            "message": f"tables from different datasources cannot be joined in the same step: {msg_parts}",
            "detail": {
                "tables_with_datasource": table_datasources,
                "step_id": step.step_id,
            },
        }
    ]


def _validate_cross_source_join(
    expr: Any,
    payload: ObjectViewPayload,
    step: PlanStep,
) -> list[SqlValidationError]:
    """校验 SQL 中多表是否来自同一数据源，禁止跨源 JOIN。"""
    if sqlglot is None:
        return []

    tables_in_query: set[str] = set()
    for t in expr.find_all(sqlglot.exp.Table):
        table_name = (t.name or "").lower()
        if table_name:
            tables_in_query.add(table_name)

    return _validate_cross_source_join_from_tables(tables_in_query, payload, step)


def _validate_sql_columns_by_ast(
    expr: Any,
    payload: ObjectViewPayload,
    step: PlanStep,
) -> list[SqlValidationError]:
    """基于 AST + scope 做字段校验，正确处理 CTE/子查询/窗口函数作用域。"""
    errors: list[SqlValidationError] = []

    if build_scope is None:
        return errors

    payload_table_columns: dict[str, set[str]] = {}
    for obj in payload.objects:
        if not obj.table:
            continue
        payload_table_columns.setdefault(obj.table.lower(), set()).update(
            (f.source_column or f.name).lower() for f in obj.fields
        )

    root_scope = build_scope(expr)
    if root_scope is None:
        return errors

    errors.extend(_validate_sql_scope(root_scope, payload_table_columns, payload, step))
    return errors


def _iter_scopes(scope: Any) -> list[Any]:
    scopes = [scope]
    for child in (
        list(getattr(scope, "cte_scopes", []))
        + list(getattr(scope, "subquery_scopes", []))
        + list(getattr(scope, "union_scopes", []))
        + list(getattr(scope, "derived_table_scopes", []))
    ):
        scopes.extend(_iter_scopes(child))
    return scopes


def _get_scope_output_columns(scope: Any) -> set[str]:
    expression = getattr(scope, "expression", None)
    if expression is None:
        return set()

    parent = getattr(expression, "parent", None)
    alias_column_names = getattr(parent, "alias_column_names", None)
    if alias_column_names:
        return {
            column.name.lower() for column in alias_column_names if getattr(column, "name", None)
        }

    output_columns: set[str] = set()
    for select_expr in getattr(expression, "selects", []):
        column_name = (getattr(select_expr, "alias_or_name", None) or "").strip().lower()
        if column_name and column_name != "*":
            output_columns.add(column_name)
    return output_columns


def _validate_sql_scope(
    root_scope: Any,
    payload_table_columns: dict[str, set[str]],
    payload: ObjectViewPayload,
    step: PlanStep,
) -> list[SqlValidationError]:
    errors: list[SqlValidationError] = []

    for scope in _iter_scopes(root_scope):
        selected_sources = getattr(scope, "selected_sources", {})
        alias_to_source_name: dict[str, str] = {}
        alias_to_columns: dict[str, set[str]] = {}
        physical_tables_in_scope: set[str] = set()

        for alias, selected in selected_sources.items():
            if not isinstance(selected, tuple) or len(selected) != 2:
                continue

            node, resolved_source = selected
            alias_lower = alias.lower()

            if isinstance(resolved_source, sqlglot.exp.Table):
                table_name = (resolved_source.name or "").lower()
                if not table_name:
                    continue
                alias_to_source_name[alias_lower] = table_name
                physical_tables_in_scope.add(table_name)
                if table_name in payload_table_columns:
                    alias_to_columns[alias_lower] = payload_table_columns[table_name]
                continue

            if build_scope is not None and hasattr(resolved_source, "expression"):
                source_name = (
                    (getattr(node, "name", None) or alias).strip().lower()
                    if node is not None
                    else alias_lower
                )
                alias_to_source_name[alias_lower] = source_name
                alias_to_columns[alias_lower] = _get_scope_output_columns(resolved_source)

        cross_errors = _validate_cross_source_join_from_tables(
            physical_tables_in_scope, payload, step
        )
        if cross_errors:
            errors.extend(cross_errors)
            continue

        select_aliases = {
            (getattr(select_expr, "alias", None) or "").strip().lower()
            for select_expr in getattr(getattr(scope, "expression", None), "selects", [])
            if (getattr(select_expr, "alias", None) or "").strip()
        }

        for col in getattr(scope, "columns", []):
            col_name_orig = (getattr(col, "alias_or_name", None) or col.name or "").strip()
            col_name = col_name_orig.lower()
            if not col_name:
                continue

            qualifier = (col.table or "").strip().lower() if col.table else ""
            qualifier_orig = (col.table or "").strip() if col.table else ""

            if not qualifier and col_name in select_aliases:
                continue

            if qualifier:
                if qualifier not in alias_to_source_name:
                    errors.append(
                        {
                            "code": "UNKNOWN_TABLE_ALIAS",
                            "message": f"unknown table alias {qualifier_orig or qualifier!r} in column {(qualifier_orig or qualifier)}.{col_name_orig!r}",
                            "detail": {
                                "alias": qualifier,
                                "identifier": col_name_orig,
                                "step_id": step.step_id,
                            },
                        }
                    )
                    continue

                source_name = alias_to_source_name[qualifier]
                source_columns = alias_to_columns.get(qualifier)
                if source_columns is None:
                    errors.append(
                        {
                            "code": "UNKNOWN_TABLE",
                            "message": f"unknown table {source_name!r} for alias {qualifier_orig or qualifier!r} in column {(qualifier_orig or qualifier)}.{col_name_orig!r}",
                            "detail": {
                                "table": source_name,
                                "alias": qualifier,
                                "identifier": col_name_orig,
                                "step_id": step.step_id,
                            },
                        }
                    )
                    continue

                if col_name not in source_columns:
                    errors.append(
                        {
                            "code": "UNKNOWN_COLUMN",
                            "message": f"column {col_name_orig!r} does not exist on table {source_name!r} (alias {qualifier_orig or qualifier!r})",
                            "detail": {
                                "identifier": col_name_orig,
                                "table": source_name,
                                "alias": qualifier,
                                "step_id": step.step_id,
                            },
                        }
                    )
                continue

            candidate_tables = sorted(
                {
                    source_name
                    for alias_name, source_name in alias_to_source_name.items()
                    if col_name in alias_to_columns.get(alias_name, set())
                }
            )
            tables_str = ", ".join(sorted(alias_to_source_name.values()))
            if len(candidate_tables) == 0:
                errors.append(
                    {
                        "code": "UNKNOWN_COLUMN",
                        "message": f"column {col_name_orig!r} does not exist in any table of current query (tables: {tables_str})",
                        "detail": {
                            "identifier": col_name_orig,
                            "tables": sorted(alias_to_source_name.values()),
                            "step_id": step.step_id,
                        },
                    }
                )
            elif len(candidate_tables) > 1:
                ambig_tables = ", ".join(candidate_tables)
                errors.append(
                    {
                        "code": "AMBIGUOUS_COLUMN",
                        "message": f"ambiguous column {col_name_orig!r} appears in multiple tables ({ambig_tables}), please qualify with table alias",
                        "detail": {
                            "identifier": col_name_orig,
                            "tables": candidate_tables,
                            "step_id": step.step_id,
                        },
                    }
                )

    return errors


def _sqlglot_dialect_validator_factory(dialect: str) -> SqlDialectValidator:
    """构造基于 sqlglot 的方言校验器：优先做语法解析，其次做通用 token 校验。"""

    def _validator(
        sql: str,
        payload: ObjectViewPayload,
        step: PlanStep,
    ) -> list[SqlValidationError]:
        errors: list[SqlValidationError] = []

        if sqlglot is not None:
            try:
                expr = sqlglot.parse_one(sql, read=dialect)
            except Exception as exc:  # pragma: no cover
                errors.append(
                    {
                        "code": "PARSE_ERROR",
                        "message": f"failed to parse SQL for db_type {dialect}: {exc}",
                        "detail": {"dialect": dialect, "step_id": step.step_id},
                    }
                )
                return errors
            errors.extend(_validate_sql_columns_by_ast(expr, payload, step))
        else:
            errors.extend(_generic_sql_token_validate(sql, payload, step))
        return errors

    return _validator


_GENERIC_SQL_VALIDATOR: SqlDialectValidator = _generic_sql_token_validate

_SQL_DIALECT_VALIDATORS: dict[str, SqlDialectValidator] = {
    "POSTGRESQL": _sqlglot_dialect_validator_factory("postgres"),
    "OPENGAUSS": _sqlglot_dialect_validator_factory("postgres"),
    "MYSQL": _sqlglot_dialect_validator_factory("mysql"),
    "SQLITE": _sqlglot_dialect_validator_factory("sqlite"),
    "CLICKHOUSE": _sqlglot_dialect_validator_factory("clickhouse"),
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


class PlanValidator:
    def validate(self, plan: QueryExecutionPlan, payload: ObjectViewPayload) -> ValidationResult:
        errors: list[str] = []
        source_ids = {s.source_id for s in payload.sources}
        step_ids = {s.step_id for s in plan.steps}

        for step in plan.steps:
            if not (step.output_ref or "").strip():
                errors.append(f"Step {step.step_id}: output_ref is required and must be non-empty")
            if step.source_id and step.source_id not in source_ids:
                errors.append(f"Step {step.step_id}: unknown source_id {step.source_id!r}")
            if step.bind_from_step and step.bind_from_step not in step_ids:
                errors.append(
                    f"Step {step.step_id}: bind_from_step {step.bind_from_step!r} not in plan"
                )
            errors.extend(self._validate_sql_step_db_type(step, payload))
            errors.extend(self._validate_sql_step_by_dialect(step, payload))
            errors.extend(self._validate_function_ids(step, payload))
            errors.extend(self._validate_api_step_params(step, payload))

        if plan.aggregation:
            agg = plan.aggregation
            if agg.strategy == "DIRECT" and agg.final_step_id is None:
                errors.append("DIRECT aggregation requires final_step_id")
            if agg.final_step_id and agg.final_step_id not in step_ids:
                errors.append(f"Aggregation final_step_id {agg.final_step_id!r} not in plan steps")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # ------------------------------------------------------------------
    # SQL step db_type validation
    # ------------------------------------------------------------------

    def _validate_sql_step_db_type(self, step: PlanStep, payload: ObjectViewPayload) -> list[str]:
        """校验 SQL 步骤对应数据源的 db_type 存在且合法。"""
        if step.type != "SQL" or not step.datasource_alias:
            return []

        source = next(
            (s for s in payload.sources if s.datasource_alias == step.datasource_alias),
            None,
        )
        if source is None:
            return []  # 由 source_id 等校验处理
        if source.source_type != "DB":
            return []

        db_type = (source.db_type or "").strip().upper()
        if not db_type:
            return [f"Step {step.step_id}: DB source {step.datasource_alias!r} missing db_type"]
        if db_type not in _SUPPORTED_DB_TYPES:
            return [
                f"Step {step.step_id}: unsupported db_type {source.db_type!r} for source {step.datasource_alias!r}"
            ]
        return []

    # ------------------------------------------------------------------
    # SQL field / 函数等引用校验（方言感知 + 通用 token）
    # ------------------------------------------------------------------

    def _validate_sql_step_by_dialect(
        self,
        step: PlanStep,
        payload: ObjectViewPayload,
    ) -> list[str]:
        """按数据源方言（db_type）做 SQL 预解析与字段/函数/token 校验。"""
        if step.type != "SQL":
            return []

        sql = step.sql_template or ""
        if not sql:
            return []

        # 无 datasource_alias 或非 DB 源时，退化为通用 token 校验
        if not step.datasource_alias:
            internal_errors = _GENERIC_SQL_VALIDATOR(sql, payload, step)
            return [self._format_sql_error(step.step_id, err) for err in internal_errors]

        source = next(
            (s for s in payload.sources if s.datasource_alias == step.datasource_alias),
            None,
        )
        if source is None or source.source_type != "DB":
            internal_errors = _GENERIC_SQL_VALIDATOR(sql, payload, step)
            return [self._format_sql_error(step.step_id, err) for err in internal_errors]

        db_type = (source.db_type or "").strip().upper()
        if not db_type:
            internal_errors = _GENERIC_SQL_VALIDATOR(sql, payload, step)
            return [self._format_sql_error(step.step_id, err) for err in internal_errors]

        validator = _SQL_DIALECT_VALIDATORS.get(db_type, _GENERIC_SQL_VALIDATOR)
        internal_errors = validator(sql, payload, step)
        return [self._format_sql_error(step.step_id, err) for err in internal_errors]

    def _format_sql_error(self, step_id: str, err: SqlValidationError) -> str:
        code = err.get("code")
        message = err.get("message", "")
        if code:
            return f"Step {step_id}: [{code}] {message}"
        return f"Step {step_id}: {message}"

    # 兼容旧的 _validate_sql_field_refs 接口：内部委托到通用 token 校验
    def _validate_sql_field_refs(self, step: PlanStep, payload: ObjectViewPayload) -> list[str]:
        sql = step.sql_template or ""
        internal_errors = _GENERIC_SQL_VALIDATOR(sql, payload, step)
        return [self._format_sql_error(step.step_id, err) for err in internal_errors]

    # ------------------------------------------------------------------
    # API step validation (object_id, function_id=actionCode, params)
    # ------------------------------------------------------------------

    def _validate_function_ids(self, step: PlanStep, payload: ObjectViewPayload) -> list[str]:
        if step.type != "API":
            return []

        if not step.object_id:
            return [f"Step {step.step_id}: object_id required for API step"]

        object_ids = {obj.object_id for obj in payload.objects}
        if step.object_id not in object_ids:
            return [f"Step {step.step_id}: unknown object_id {step.object_id!r}"]

        if not step.function_id:
            return [f"Step {step.step_id}: function_id (actionCode) required for API step"]

        obj = next(o for o in payload.objects if o.object_id == step.object_id)
        action_codes = {a.action_code for a in obj.actions}
        if step.function_id not in action_codes:
            return [
                f"Step {step.step_id}: unknown action_code {step.function_id!r} for object {step.object_id!r}"
            ]
        return []

    def _validate_api_step_params(self, step: PlanStep, payload: ObjectViewPayload) -> list[str]:
        if step.type != "API" or not step.object_id or not step.function_id:
            return []

        obj = next((o for o in payload.objects if o.object_id == step.object_id), None)
        if obj is None:
            return []

        action = next((a for a in obj.actions if a.action_code == step.function_id), None)
        if action is None:
            return []

        in_params = action.input_params
        in_codes = {p.param_code for p in in_params}
        required_codes = {p.param_code for p in in_params if p.required}

        errors: list[str] = []
        for code in required_codes:
            if code not in step.params:
                errors.append(
                    f"Step {step.step_id}: missing required param {code!r} for action {step.function_id!r}"
                )
        for key in step.params:
            if key not in in_codes:
                errors.append(
                    f"Step {step.step_id}: unknown param {key!r} for action {step.function_id!r}"
                )
        return errors
