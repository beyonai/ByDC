"""ExecutionObjectConverter: PlanStep -> ExecTask 对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datacloud_data_sdk.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data_sdk.plan.param_converter import map_to_physical
from datacloud_data_sdk.plan.models import (
    ObjectViewFunction,
    ObjectViewPayload,
    QueryExecutionPlan,
    PlanStep,
)

if TYPE_CHECKING:
    from datacloud_data_sdk.plan.term_resolver import TermResolver


class ExecutionObjectConverter:
    def __init__(self, term_resolver: "TermResolver | None" = None) -> None:
        self._term_resolver = term_resolver

    def convert(
        self,
        plan: QueryExecutionPlan,
        payload: ObjectViewPayload | None = None,
    ) -> list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask]:
        tasks: list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask] = []
        for step in plan.steps:
            tasks.append(self._convert_step(step, payload))
        return tasks

    def _convert_step(
        self,
        step: PlanStep,
        payload: ObjectViewPayload | None = None,
    ) -> SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask:
        if step.type == "SQL":
            return SqlExecTask(
                datasource_alias=step.datasource_alias,
                sql_template=step.sql_template,
                output_ref=step.output_ref,
                bind_from_step=step.bind_from_step,
                bind_key=step.bind_key,
            )
        elif step.type == "API":
            params = step.params
            if payload and step.function_id:
                fn = self._find_function(step.function_id, payload)
                if fn:
                    in_params = [p for p in fn.params if p.direction == "IN"]
                    if self._term_resolver and in_params:
                        params = self._term_resolver.resolve_params(step.params, in_params)
                    params = map_to_physical(params, in_params)
            return ApiExecTask(
                function_code=step.function_id,
                params=params,
                output_ref=step.output_ref,
                csv_table_name=step.csv_table_name,
                bind_from_step=step.bind_from_step,
                bind_key=step.bind_key,
            )
        elif step.type == "SCRIPT":
            return ScriptExecTask(
                action_code=step.action_code,
                script=step.script,
                params=step.params,
                output_ref=step.output_ref,
            )
        elif step.type == "KB":
            return KbExecTask(
                datasource_alias=step.datasource_alias,
                query=step.query,
                tags=step.tags,
                output_ref=step.output_ref,
            )
        else:
            raise ValueError(f"Unknown step type: {step.type!r}")

    def _find_function(
        self, function_id: str, payload: ObjectViewPayload
    ) -> ObjectViewFunction | None:
        for obj in payload.objects:
            for fn in obj.functions:
                if fn.function_code == function_id:
                    return fn
        return None
