"""ExecutionObjectConverter: PlanStep -> ExecTask 对象。"""
from __future__ import annotations

from datacloud_data_sdk.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data_sdk.plan.models import QueryExecutionPlan, PlanStep


class ExecutionObjectConverter:
    def convert(self, plan: QueryExecutionPlan) -> list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask]:
        tasks: list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask] = []
        for step in plan.steps:
            tasks.append(self._convert_step(step))
        return tasks

    def _convert_step(self, step: PlanStep) -> SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask:
        if step.type == "SQL":
            return SqlExecTask(
                datasource_alias=step.datasource_alias,
                sql_template=step.sql_template,
                output_ref=step.output_ref,
                bind_from_step=step.bind_from_step,
                bind_key=step.bind_key,
            )
        elif step.type == "API":
            return ApiExecTask(
                function_code=step.function_id,
                params=step.params,
                output_ref=step.output_ref,
                csv_table_name=step.csv_table_name,
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
