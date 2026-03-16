"""ExecutionObjectConverter: PlanStep -> ExecTask 对象。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data_sdk.plan.param_converter import map_to_physical, _to_function_param
from datacloud_data_sdk.plan.models import (
    ObjectViewField,
    ObjectViewPayload,
    QueryExecutionPlan,
    PlanStep,
)
from datacloud_data_sdk.plan.sql_term_resolver import resolve_sql_literals

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_sdk.plan.term_resolver import TermResolver


class ExecutionObjectConverter:
    def __init__(
        self,
        term_resolver: "TermResolver | None" = None,
        loader: "OntologyLoader | None" = None,
    ) -> None:
        self._term_resolver = term_resolver
        self._loader = loader

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
            sql_template = step.sql_template
            if self._term_resolver and payload and self._term_resolver.term_loader:
                sql_template = resolve_sql_literals(
                    sql_template,
                    payload,
                    step.datasource_alias,
                    self._term_resolver.term_loader,
                )
            return SqlExecTask(
                datasource_alias=step.datasource_alias,
                sql_template=sql_template,
                output_ref=step.output_ref,
                bind_from_step=step.bind_from_step,
                bind_key=step.bind_key,
            )
        elif step.type == "API":
            return self._convert_api_step(step, payload)
        elif step.type == "KB":
            tags: dict[str, Any] = dict(step.tags)
            if self._term_resolver and payload and tags:
                field_specs = self._collect_fields_for_tags(payload, list(tags.keys()))
                if field_specs:
                    tags = self._term_resolver.resolve_fields(tags, field_specs)
            return KbExecTask(
                datasource_alias=step.datasource_alias,
                query=step.query,
                tags=tags,
                output_ref=step.output_ref,
            )
        else:
            raise ValueError(f"Unknown step type: {step.type!r}")

    def _collect_fields_for_tags(
        self, payload: ObjectViewPayload, tag_keys: list[str]
    ) -> list[ObjectViewField]:
        """从 payload 中收集 tags 对应且含 term_set 的 field。"""
        key_set = set(tag_keys)
        result: list[ObjectViewField] = []
        seen: set[str] = set()
        for obj in payload.objects:
            for f in obj.fields:
                if f.name in key_set and f.term_set and f.name not in seen:
                    result.append(f)
                    seen.add(f.name)
        return result

    def _convert_api_step(
        self,
        step: PlanStep,
        payload: ObjectViewPayload | None,
    ) -> ApiExecTask | ScriptExecTask:
        if not step.object_id:
            raise ValueError(
                f"Step {step.step_id}: object_id required for API step"
            )
        if not self._loader:
            raise ValueError(
                "ExecutionObjectConverter requires loader for API steps"
            )

        action = self._loader.get_action(step.object_id, step.function_id)
        ontology_action = action._action

        if ontology_action.script:
            return ScriptExecTask(
                action_code=step.function_id,
                script=ontology_action.script,
                params=step.params,
                output_ref=step.output_ref,
            )

        if not ontology_action.function_refs:
            from datacloud_data_sdk.exceptions import ActionNotConfiguredError

            raise ActionNotConfiguredError(ontology_action.action_code)

        params: dict[str, Any] = dict(step.params)

        in_params = [
            _to_function_param(p)
            for p in ontology_action.params
            if p.direction in ("IN", "INOUT")
        ]
        if self._term_resolver and in_params:
            params = self._term_resolver.resolve_params(params, in_params)
        physical_params = map_to_physical(params, in_params)

        return ApiExecTask(
            object_code=step.object_id,
            action_code=step.function_id,
            params=physical_params,
            output_ref=step.output_ref,
            bind_from_step=step.bind_from_step,
            bind_key=step.bind_key,
        )
