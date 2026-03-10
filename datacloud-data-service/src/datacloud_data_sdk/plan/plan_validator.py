"""PlanValidator: 校验 QueryExecutionPlan 合法性。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from datacloud_data_sdk.plan.models import (
    ObjectViewPayload,
    PlanStep,
    QueryExecutionPlan,
)

_SQL_KEYWORDS = {
    "select", "from", "where", "join", "on", "and", "or", "not", "in",
    "between", "like", "is", "null", "as", "order", "by", "group",
    "having", "limit", "offset", "distinct", "all", "union", "intersect",
    "except", "exists", "case", "when", "then", "else", "end", "asc",
    "desc", "inner", "left", "right", "outer", "cross", "full", "insert",
    "update", "delete", "create", "drop", "alter", "into", "values",
    "set", "table", "index", "view", "true", "false", "with",
}

_SQL_FUNCTIONS = {
    "count", "sum", "avg", "max", "min", "coalesce", "ifnull",
    "cast", "convert", "upper", "lower", "trim", "length", "substr",
    "substring", "concat", "replace", "round", "abs", "ceil", "floor",
    "now", "date", "year", "month", "day", "hour", "minute", "second",
    "iif", "nullif", "group_concat", "date_format", "str_to_date",
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
    # API function_id validation
    # ------------------------------------------------------------------

    def _validate_function_ids(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
        if step.type != "API" or not step.function_id:
            return []

        known_functions = {
            fn.function_code
            for obj in payload.objects
            for fn in obj.functions
        }
        if step.function_id not in known_functions:
            return [
                f"Step {step.step_id}: unknown function_id {step.function_id!r}"
            ]
        return []

    def _validate_api_step_params(
        self, step: PlanStep, payload: ObjectViewPayload
    ) -> list[str]:
        if step.type != "API" or not step.function_id:
            return []

        fn = None
        for obj in payload.objects:
            for f in obj.functions:
                if f.function_code == step.function_id:
                    fn = f
                    break
            if fn is not None:
                break
        if fn is None:
            return []

        in_params = [p for p in fn.params if p.direction == "IN"]
        in_codes = {p.param_code for p in in_params}
        required_codes = {p.param_code for p in in_params if p.required}

        errors: list[str] = []
        for code in required_codes:
            if code not in step.params:
                errors.append(
                    f"Step {step.step_id}: missing required param {code!r} for function {step.function_id!r}"
                )
        for key in step.params:
            if key not in in_codes:
                errors.append(
                    f"Step {step.step_id}: unknown param {key!r} for function {step.function_id!r}"
                )
        return errors
