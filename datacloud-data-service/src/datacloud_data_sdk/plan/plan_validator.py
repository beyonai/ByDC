"""PlanValidator: 校验 QueryExecutionPlan 合法性。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from datacloud_data_sdk.plan.models import (
    ObjectViewPayload,
    PlanStep,
    QueryExecutionPlan,
)

_SUPPORTED_DB_TYPES = {"POSTGRESQL", "MYSQL", "OPENGAUSS", "SQLITE", "CLICKHOUSE"}

_SQL_KEYWORDS = {
    "select", "from", "where", "join", "on", "and", "or", "not", "in",
    "between", "like", "is", "null", "as", "order", "by", "group",
    "having", "limit", "offset", "distinct", "all", "union", "intersect",
    "except", "exists", "case", "when", "then", "else", "end", "asc",
    "desc", "inner", "left", "right", "outer", "cross", "full", "insert",
    "update", "delete", "create", "drop", "alter", "into", "values",
    "set", "table", "index", "view", "true", "false", "with",
    "interval", "over", "partition", "range", "rows", "unbounded",
    "preceding", "following", "default",
}

_SQL_FUNCTIONS = {
    # 聚合
    "count", "sum", "avg", "max", "min", "group_concat", "string_agg",
    "array_agg", "json_agg", "json_build_object",
    # 空值/类型
    "coalesce", "ifnull", "nullif", "cast", "convert",
    # 字符串
    "upper", "lower", "trim", "ltrim", "rtrim", "length", "char_length",
    "substr", "substring", "concat", "concat_ws", "replace",
    "position", "strpos", "split_part", "left", "right", "lpad", "rpad",
    "regexp_replace", "regexp_match", "repeat",
    # 数值
    "round", "abs", "ceil", "floor", "mod", "power", "sqrt", "random",
    "greatest", "least",
    # 日期时间 - 标准/PostgreSQL/OpenGauss
    "now", "current_date", "current_time", "current_timestamp",
    "localtime", "localtimestamp",
    "date", "year", "month", "day", "hour", "minute", "second",
    "extract", "date_trunc", "age", "make_date", "make_interval",
    "to_char", "to_date", "to_timestamp", "date_part",
    "date_format", "str_to_date", "date_add", "date_sub",
    # 条件
    "iif",
    # 窗口
    "row_number", "rank", "dense_rank", "lag", "lead",
    "first_value", "last_value", "ntile",
    # 其他
    "unnest", "generate_series",
}

_IDENTIFIER_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
_ALIAS_AS_RE = re.compile(r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE)
_TABLE_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


class PlanValidator:
    def validate(
        self, plan: QueryExecutionPlan, payload: ObjectViewPayload
    ) -> ValidationResult:
        errors: list[str] = []
        source_ids = {s.source_id for s in payload.sources}
        step_ids = {s.step_id for s in plan.steps}

        for step in plan.steps:
            if step.source_id and step.source_id not in source_ids:
                errors.append(
                    f"Step {step.step_id}: unknown source_id {step.source_id!r}"
                )
            if step.bind_from_step and step.bind_from_step not in step_ids:
                errors.append(
                    f"Step {step.step_id}: bind_from_step {step.bind_from_step!r} not in plan"
                )
            errors.extend(self._validate_sql_field_refs(step, payload))
            errors.extend(self._validate_sql_step_db_type(step, payload))
            errors.extend(self._validate_function_ids(step, payload))
            errors.extend(self._validate_api_step_params(step, payload))

        if plan.aggregation:
            agg = plan.aggregation
            if agg.strategy == "DIRECT" and agg.final_step_id is None:
                errors.append("DIRECT aggregation requires final_step_id")
            if agg.final_step_id and agg.final_step_id not in step_ids:
                errors.append(
                    f"Aggregation final_step_id {agg.final_step_id!r} not in plan steps"
                )

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # ------------------------------------------------------------------
    # SQL step db_type validation
    # ------------------------------------------------------------------

    def _validate_sql_step_db_type(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
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
            return [
                f"Step {step.step_id}: DB source {step.datasource_alias!r} missing db_type"
            ]
        if db_type not in _SUPPORTED_DB_TYPES:
            return [
                f"Step {step.step_id}: unsupported db_type {source.db_type!r} for source {step.datasource_alias!r}"
            ]
        return []

    # ------------------------------------------------------------------
    # SQL field-reference validation
    # ------------------------------------------------------------------

    def _validate_sql_field_refs(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
        sql = step.sql_template
        if not sql:
            return []

        # Strip string literals and numeric literals
        cleaned = re.sub(r"'[^']*'", "", sql)
        cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", "", cleaned)

        tokens = set(_IDENTIFIER_RE.findall(cleaned))

        known: set[str] = set()
        for obj in payload.objects:
            if obj.table:
                known.add(obj.table.lower())
            for f in obj.fields:
                known.add(f.name.lower())
                if f.source_column:
                    known.add(f.source_column.lower())

        # Extract aliases (AS alias, and table aliases like FROM t alias)
        aliases: set[str] = set()
        for m in _ALIAS_AS_RE.finditer(cleaned):
            aliases.add(m.group(1).lower())
        for m in _TABLE_ALIAS_RE.finditer(cleaned):
            candidate = m.group(2).lower()
            if candidate not in _SQL_KEYWORDS:
                aliases.add(candidate)

        valid = _SQL_KEYWORDS | _SQL_FUNCTIONS | known | aliases

        errors: list[str] = []
        for token in sorted(tokens):
            if token.lower() not in valid:
                errors.append(
                    f"Step {step.step_id}: SQL references unknown column {token!r}"
                )
        return errors

    # ------------------------------------------------------------------
    # API step validation (object_id, function_id=actionCode, params)
    # ------------------------------------------------------------------

    def _validate_function_ids(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
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

    def _validate_api_step_params(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
        if step.type != "API" or not step.object_id or not step.function_id:
            return []

        obj = next((o for o in payload.objects if o.object_id == step.object_id), None)
        if obj is None:
            return []

        action = next(
            (a for a in obj.actions if a.action_code == step.function_id), None
        )
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
