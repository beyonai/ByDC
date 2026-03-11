"""Object 实体：本体对象的运行时表示。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.action import Action
from datacloud_data_sdk.exceptions import ActionNotFoundError
from datacloud_data_sdk.ontology.models import OntologyAction, OntologyClass
from datacloud_data_sdk.relation import Relation


class Object:
    """本体对象实体，提供自生说明、动作调用与查询能力。

    通过 OntologyLoader.get_object() 获取实例。
    """

    def __init__(self, ontology_class: OntologyClass, relations: list[Relation], loader: Any = None) -> None:
        self._cls = ontology_class
        self._relations = relations
        self._loader = loader

    @property
    def object_code(self) -> str:
        return self._cls.object_code

    def get_description(self) -> str:
        """生成 Markdown 格式的对象自生说明。"""
        lines = [
            f"## 对象：{self._cls.object_name}（{self._cls.object_code}）",
            "",
            f"**数据来源**：{self._cls.source_type}"
            + (f"（{self._cls.datasource_alias}）" if self._cls.datasource_alias else "")
            + (f"，表 `{self._cls.table_name}`" if self._cls.table_name else ""),
            "",
            "**字段**：",
        ]
        for f in self._cls.fields:
            aliases = "，".join([f.field_name] + f.aliases)
            line = f"- {f.field_code}（{aliases}, {f.field_type}）"
            if f.description:
                line += f" —— {f.description}"
            lines.append(line)

        if self._cls.actions:
            lines += ["", "**动作**："]
            for a in self._cls.actions:
                exec_type = "脚本" if a.script else "API"
                in_params = ", ".join(
                    f"{p.param_code}({'必填' if p.required else '可选'})"
                    for p in a.params
                    if p.direction in ("IN", "INOUT")
                )
                lines.append(
                    f"- `{a.action_code}`（{exec_type}）：{a.action_name}，入参：{in_params}"
                )

        if self._relations:
            lines += ["", "**关联**："]
            for r in self._relations:
                other = r.to_object if r.from_object == self._cls.object_code else r.from_object
                line = f"- 关联 {other}，{r.cardinality}"
                if r.description:
                    line += f" —— {r.description}"
                lines.append(line)

        return "\n".join(lines)

    def get_action_schema(self, action_code: str) -> dict[str, object]:
        """获取动作的 input/output JSON Schema。"""
        action = self._find_action(action_code)
        return Action(action, loader=self._loader).get_schema()

    def list_action_codes(self) -> list[str]:
        return [a.action_code for a in self._cls.actions]

    def get_relations(self) -> list[Relation]:
        return self._relations

    def _find_action(self, action_code: str) -> OntologyAction:
        for a in self._cls.actions:
            if a.action_code == action_code:
                return a
        raise ActionNotFoundError(self._cls.object_code, action_code)

    async def query(self, question: str, include_plan: bool = True) -> dict[str, object]:
        """自然语言查询：计划 -> 执行 -> 聚合完整管线。"""
        import uuid
        from dataclasses import asdict

        from datacloud_data_sdk.plan.object_view_builder import ObjectViewBuilder
        from datacloud_data_sdk.plan.plan_validator import PlanValidator
        from datacloud_data_sdk.plan.execution_object_converter import ExecutionObjectConverter
        from datacloud_data_sdk.plan.data_permission_rewriter import DataPermissionRewriter
        from datacloud_data_sdk.executor.executor import Executor
        from datacloud_data_sdk.executor.kb_executor import KbExecutor
        from datacloud_data_sdk.aggregator.direct_aggregator import DirectAggregator
        from datacloud_data_sdk.aggregator.sqlite_aggregator import SqliteAggregator
        from datacloud_data_sdk.context import get_current_context
        from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
        from datacloud_data_sdk.exceptions import PlanValidationError, CannotAnswerError

        if not hasattr(self, '_loader') or self._loader is None:
            raise NotImplementedError("Object.query requires OntologyLoader with configured plan_generator")

        loader = self._loader
        config = loader._config
        if config.plan_generator is None:
            raise NotImplementedError("Call loader.configure(plan_generator=...) first")

        request_id = str(uuid.uuid4())
        trace_id = request_id[:8]
        csv_manager = CsvStorageManager(config.csv_base_dir)
        observer = None
        if config.event_bus:
            from datacloud_data_sdk.events.query_observer import QueryObserver

            observer = QueryObserver(config.event_bus, trace_id=trace_id)

        try:
            object_ids = [self._cls.object_code]
            if observer:
                try:
                    await observer.on_query_start(request_id, question, object_ids)
                except Exception:
                    pass
            builder = ObjectViewBuilder(loader)
            payload = builder.build(object_ids=object_ids, view_id=request_id)
            if observer:
                try:
                    await observer.on_view_built(request_id, asdict(payload))
                except Exception:
                    pass

            max_retries = getattr(config.plan_generator, "_max_retries", 2)
            validation_errors_list: list[str] | None = None
            plan = None
            result = None
            for retry in range(max_retries + 1):
                plan = await config.plan_generator.generate(
                    payload,
                    question,
                    validation_errors=validation_errors_list,
                    term_loader=getattr(config, "term_loader", None),
                )
                plan_dict = {
                    "question": plan.question,
                    "can_answer": plan.can_answer,
                    "clarification": plan.clarification,
                    "steps": [asdict(s) for s in plan.steps],
                    "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                }
                if observer:
                    try:
                        await observer.on_plan_generated(request_id, plan_dict)
                    except Exception:
                        pass
                try:
                    import json
                    import logging
                    logging.getLogger("datacloud_data_sdk").info(
                        json.dumps(plan_dict, ensure_ascii=False)
                    )
                except Exception:
                    pass

                if not plan.can_answer:
                    raise CannotAnswerError(plan.clarification)

                result = PlanValidator().validate(plan, payload)
                if observer:
                    try:
                        plan_dict = {
                            "question": plan.question,
                            "can_answer": plan.can_answer,
                            "steps": [asdict(s) for s in plan.steps],
                            "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                        }
                        await observer.on_plan_validated(
                            request_id,
                            result.valid,
                            plan_dict,
                            asdict(payload),
                            question,
                            result.errors,
                            retry,
                        )
                    except Exception:
                        pass
                if result.valid:
                    break
                validation_errors_list = result.errors
                if retry >= max_retries:
                    if observer:
                        try:
                            plan_dict = {
                                "steps": [asdict(s) for s in plan.steps],
                                "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                            }
                            await observer.on_plan_validation_failed(
                                request_id, result.errors, plan_dict
                            )
                        except Exception:
                            pass
                    raise PlanValidationError(result.errors)

            try:
                ctx = get_current_context()
                plan = DataPermissionRewriter().rewrite(plan, ctx)
            except Exception:
                pass
            if observer:
                try:
                    await observer.on_plan_rewritten(
                        request_id,
                        {
                            "steps": [asdict(s) for s in plan.steps],
                            "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                        },
                    )
                except Exception:
                    pass

            term_resolver = None
            if getattr(config, "term_loader", None):
                from datacloud_data_sdk.plan.term_resolver import TermResolver

                term_resolver = TermResolver(config.term_loader)
            tasks = ExecutionObjectConverter(
                term_resolver=term_resolver, loader=loader
            ).convert(plan, payload)
            if observer:
                try:
                    tasks_dict = [asdict(t) for t in tasks]
                    agg_dict = asdict(plan.aggregation) if plan.aggregation else {}
                    await observer.on_execution_tasks_ready(
                        request_id, tasks_dict, agg_dict
                    )
                except Exception:
                    pass

            from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor
            from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
            from datacloud_data_sdk.executor.api_executor import ApiExecutor
            from datacloud_data_sdk.executor.script_executor import ScriptExecutor

            ds_manager = DataSourceManager(config.datasource_configs) if config.datasource_configs else None
            sql_exec = SqlExecutor(ds_manager, config.csv_base_dir) if ds_manager else None
            api_exec = ApiExecutor(loader._functions, config.csv_base_dir) if loader._functions else None
            script_exec = ScriptExecutor(loader)
            kb_exec = (
                KbExecutor(config.kb_source_configs, config.csv_base_dir)
                if config.kb_source_configs
                else None
            )

            executor = Executor(
                sql_executor=sql_exec,
                api_executor=api_exec,
                script_executor=script_exec,
                kb_executor=kb_exec,
                csv_base_dir=config.csv_base_dir,
            )

            step_results = await executor.run(
                tasks, request_id, step_ids=[s.step_id for s in plan.steps]
            )
            if observer:
                try:
                    await observer.on_steps_executed(request_id, step_results.to_legacy_dict())
                except Exception:
                    pass

            if plan.aggregation:
                if plan.aggregation.strategy == "SQLITE_MEM":
                    records = await SqliteAggregator().aggregate(plan.aggregation, step_results)
                else:
                    records = await DirectAggregator().aggregate(plan.aggregation, step_results)
            else:
                records = []
            columns = plan.aggregation.columns if plan.aggregation else []
            if observer:
                try:
                    await observer.on_aggregation_completed(
                        request_id, records, columns
                    )
                except Exception:
                    pass

            result = {
                "records": records,
                "meta": {
                    "objectId": self._cls.object_code,
                    "objectName": self._cls.object_name,
                    "columns": list(columns),
                    "total": len(records),
                },
                "trace": {
                    "request_id": request_id,
                    "question": question,
                    "object_id": self._cls.object_code,
                },
            }
            if include_plan:
                result["plan"] = {
                    "question": plan.question,
                    "can_answer": plan.can_answer,
                    "clarification": plan.clarification,
                    "steps": [asdict(s) for s in plan.steps],
                    "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                }
            return result

        except Exception as exc:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(exc, request_id=request_id, trace_id=trace_id)
            raise
        finally:
            csv_manager.cleanup(request_id)

    async def invoke_action(
        self, action_code: str, params: dict[str, object]
    ) -> dict[str, object]:
        """执行动作（执行层实现后补全）。"""
        action = self._find_action(action_code)
        return await Action(action, loader=self._loader).execute(params)
