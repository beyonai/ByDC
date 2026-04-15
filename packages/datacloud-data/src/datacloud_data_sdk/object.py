"""
对象(Object)实体模块

本模块定义了 Object 类，作为本体对象的运行时表示。
Object 封装了 OntologyClass 及其关联关系，提供自生说明、动作调用与查询能力。

核心功能：
- 自生说明：生成 Markdown 格式的对象文档，包含字段、动作、关联等信息
- 动作管理：列出、获取、执行对象上的动作
- 自然语言查询：通过 LLM 将自然语言转换为查询计划并执行

使用示例：
    obj = loader.get_object("po_users")
    description = obj.get_description()  # 获取对象说明
    result = await obj.query("查询所有活跃用户")  # 自然语言查询
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_data_sdk.action import Action
from datacloud_data_sdk.exceptions import ActionNotFoundError
from datacloud_data_sdk.ontology.models import OntologyAction, OntologyClass
from datacloud_data_sdk.relation import Relation

logger = logging.getLogger(__name__)


class Object:
    """
    本体对象实体类

    提供对象的自生说明、动作调用与查询能力。
    通过 OntologyLoader.get_object() 获取实例。

    Attributes:
        _cls: 本体类定义
        _relations: 对象的关联关系列表
        _loader: 本体加载器引用

    Example:
        obj = loader.get_object("po_users")
        print(obj.get_description())
        result = await obj.query("查询部门为研发的用户")
    """

    def __init__(
        self, ontology_class: OntologyClass, relations: list[Relation], loader: Any = None
    ) -> None:
        """
        初始化对象实体

        Args:
            ontology_class: 本体类定义
            relations: 对象的关联关系列表
            loader: 本体加载器实例
        """
        self._cls = ontology_class
        self._relations = relations
        self._loader = loader

    @property
    def object_code(self) -> str:
        """对象代码，唯一标识此对象"""
        return self._cls.object_code

    def get_description(self) -> str:
        """
        生成 Markdown 格式的对象自生说明

        包含以下信息：
        - 对象名称和代码
        - 数据来源（数据源、表名）
        - 字段列表（代码、名称、类型、描述）
        - 动作列表（代码、类型、入参）
        - 关联关系

        Returns:
            str: Markdown 格式的对象说明文档
        """
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
        """
        获取动作的 JSON Schema

        Args:
            action_code: 动作代码

        Returns:
            dict: 包含 name, title, description, inputSchema, outputSchema 的字典

        Raises:
            ActionNotFoundError: 动作不存在时抛出
        """
        action = self._find_action(action_code)
        return Action(action, loader=self._loader).get_schema()

    def list_action_codes(self) -> list[str]:
        """
        列出对象上所有动作的代码

        Returns:
            list[str]: 动作代码列表
        """
        return [a.action_code for a in self._cls.actions]

    def get_relations(self) -> list[Relation]:
        """
        获取对象的关联关系列表

        Returns:
            list[Relation]: 关联关系列表
        """
        return self._relations

    def _find_action(self, action_code: str) -> OntologyAction:
        """
        查找指定代码的动作

        Args:
            action_code: 动作代码

        Returns:
            OntologyAction: 找到的动作定义

        Raises:
            ActionNotFoundError: 动作不存在时抛出
        """
        for a in self._cls.actions:
            if a.action_code == action_code:
                return a
        raise ActionNotFoundError(self._cls.object_code, action_code)

    async def query(
        self,
        question: str,
        include_plan: bool = True,
        knowledge_context: str | None = None,
    ) -> dict[str, object]:
        """
        自然语言查询

        完整的查询管线：
        1. 构建对象视图载荷
        2. 生成查询计划（通过 LLM）
        3. 验证计划
        4. 应用数据权限重写
        5. 转换为执行任务
        6. 执行查询
        7. 聚合结果

        Args:
            question: 自然语言查询问题
            include_plan: 是否在结果中包含执行计划
            knowledge_context: 可选的知识增强上下文，会传递给查询计划生成模型

        Returns:
            dict: 查询结果，包含 records, total, meta 等字段

        Raises:
            CannotAnswerError: 无法回答问题时抛出
            PlanValidationError: 计划验证失败时抛出
        """
        import uuid
        from dataclasses import asdict

        from datacloud_data_sdk.aggregator.direct_aggregator import DirectAggregator
        from datacloud_data_sdk.aggregator.sqlite_aggregator import SqliteAggregator
        from datacloud_data_sdk.context import get_current_context
        from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
        from datacloud_data_sdk.exceptions import (
            CannotAnswerError,
            PlanValidationError,
            TermAmbiguousError,
            TermNotFoundError,
        )
        from datacloud_data_sdk.executor.executor import Executor
        from datacloud_data_sdk.executor.kb_executor import KbExecutor
        from datacloud_data_sdk.plan.execution_object_converter import ExecutionObjectConverter
        from datacloud_data_sdk.plan.object_view_builder import ObjectViewBuilder

        if not hasattr(self, "_loader") or self._loader is None:
            raise NotImplementedError(
                "Object.query requires OntologyLoader with configured plan_generator"
            )

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

        # 初始化 Gateway 进度推送器（从 InvocationContext 中取 gateway_context）
        gw_reporter = None
        try:
            from datacloud_data_sdk.context import get_gateway_context
            from datacloud_data_sdk.events.gateway_reporter import GatewayProgressReporter

            _gw_ctx = get_gateway_context()
            if _gw_ctx is not None:
                gw_reporter = GatewayProgressReporter(_gw_ctx)
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

        try:
            object_ids = [self._cls.object_code]
            if observer:
                try:
                    await observer.on_query_start(request_id, question, object_ids)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            builder = ObjectViewBuilder(loader)
            payload = builder.build(object_ids=object_ids, view_id=request_id)
            if observer:
                try:
                    await observer.on_view_built(request_id, asdict(payload))
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            plan = await config.plan_generator.generate(
                payload,
                question,
                knowledge_context=knowledge_context,
                term_loader=getattr(config, "term_loader", None),
            )
            if not plan.can_answer:
                raise CannotAnswerError(plan.clarification)
            plan_dict = {
                "question": plan.question,
                "can_answer": plan.can_answer,
                "clarification": plan.clarification,
                "steps": [asdict(s) for s in plan.steps],
                "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
            }
            if gw_reporter:
                try:
                    _step_types = " → ".join(
                        f"{s.step_id}({getattr(s, 'step_type', 'SQL')})" for s in plan.steps
                    )
                    await gw_reporter.on_plan_generated(f"共 {len(plan.steps)} 步：{_step_types}")
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            if observer:
                try:
                    await observer.on_plan_generated(request_id, plan_dict)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            try:
                import json

                logging.getLogger("datacloud_data_sdk").info(
                    json.dumps(plan_dict, ensure_ascii=False)
                )
            except Exception:
                logger.debug("observer/reporter callback failed", exc_info=True)

            if observer:
                try:
                    await observer.on_plan_validated(
                        request_id,
                        True,
                        plan_dict,
                        asdict(payload),
                        question,
                        [],
                        0,
                    )
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            try:
                get_current_context()
                # plan = DataPermissionRewriter().rewrite(plan, ctx)
            except Exception:
                logger.debug("observer/reporter callback failed", exc_info=True)
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
                    logger.debug("observer/reporter callback failed", exc_info=True)

            term_resolver = None
            if getattr(config, "term_loader", None):
                from datacloud_data_sdk.plan.term_resolver import TermResolver

                term_resolver = TermResolver(config.term_loader)
            tasks = ExecutionObjectConverter(term_resolver=term_resolver, loader=loader).convert(
                plan, payload
            )
            if observer:
                try:
                    tasks_dict = [asdict(t) for t in tasks]
                    agg_dict = asdict(plan.aggregation) if plan.aggregation else {}
                    await observer.on_execution_tasks_ready(request_id, tasks_dict, agg_dict)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            from datacloud_data_sdk.executor.api_executor import ApiExecutor
            from datacloud_data_sdk.executor.script_executor import ScriptExecutor
            from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
            from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor

            ds_manager = (
                DataSourceManager(config.datasource_configs) if config.datasource_configs else None
            )
            sql_exec = SqlExecutor(ds_manager, config.csv_base_dir) if ds_manager else None
            api_exec = ApiExecutor(loader, config.csv_base_dir) if loader else None
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

            if gw_reporter:
                try:
                    for _s in plan.steps:
                        _stype = getattr(_s, "step_type", type(_s).__name__)
                        _sdesc = getattr(_s, "sql_template", None) or getattr(_s, "function_id", "")
                        await gw_reporter.on_step_executing(_s.step_id, _stype, str(_sdesc)[:60])
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            step_results = await executor.run(
                tasks, request_id, step_ids=[s.step_id for s in plan.steps]
            )

            if gw_reporter:
                try:
                    for _s in plan.steps:
                        await gw_reporter.on_step_completed(_s.step_id)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            if observer:
                try:
                    await observer.on_steps_executed(request_id, step_results.to_legacy_dict())
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            if plan.aggregation:
                if gw_reporter:
                    try:
                        await gw_reporter.on_aggregating(plan.aggregation.strategy)
                    except Exception:
                        logger.debug("observer/reporter callback failed", exc_info=True)
                if plan.aggregation.strategy == "SQLITE_MEM":
                    records = await SqliteAggregator().aggregate(plan.aggregation, step_results)
                else:
                    records = await DirectAggregator().aggregate(plan.aggregation, step_results)
            else:
                records = []
            columns = plan.aggregation.columns if plan.aggregation else []
            if gw_reporter:
                try:
                    await gw_reporter.on_aggregation_completed(len(records))
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            if observer:
                try:
                    await observer.on_aggregation_completed(request_id, records, columns)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)

            from datacloud_data_sdk.result_formatter import build_query_response

            raw_result: dict[str, object] = {
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
            logger.info(
                "object.query done: object_code=%s record_count=%s aggregation=%s final_step=%s",
                self._cls.object_code,
                len(records),
                getattr(plan.aggregation, "strategy", None) if plan.aggregation else None,
                getattr(plan.aggregation, "final_step_id", None) if plan.aggregation else None,
            )
            if include_plan:
                raw_result["plan"] = {
                    "question": plan.question,
                    "can_answer": plan.can_answer,
                    "clarification": plan.clarification,
                    "steps": [asdict(s) for s in plan.steps],
                    "aggregation": asdict(plan.aggregation) if plan.aggregation else None,
                }
            return build_query_response(
                raw_result,
                csv_manager=csv_manager,
                threshold=config.query_result_csv_threshold,
                preview_rows=config.query_result_preview_rows,
            )

        except CannotAnswerError as exc:
            from datacloud_data_sdk.result_formatter import build_error_data

            return build_error_data(
                str(exc),
                result_type="rejected",
                trace={
                    "request_id": request_id,
                    "question": question,
                    "object_id": self._cls.object_code,
                },
            )
        except (TermNotFoundError, TermAmbiguousError) as exc:
            from datacloud_data_sdk.result_formatter import build_error_data

            return build_error_data(
                str(exc),
                result_type="ask_user",
                trace={
                    "request_id": request_id,
                    "question": question,
                    "object_id": self._cls.object_code,
                },
            )
        except PlanValidationError as exc:
            if observer:
                try:
                    plan_dict: dict = {}
                    if exc.plan:
                        plan_dict = {
                            "steps": [asdict(s) for s in exc.plan.steps],
                            "aggregation": (
                                asdict(exc.plan.aggregation) if exc.plan.aggregation else None
                            ),
                        }
                    await observer.on_plan_validation_failed(request_id, exc.errors, plan_dict)
                except Exception:
                    logger.debug("observer/reporter callback failed", exc_info=True)
            raise
        except Exception as exc:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(exc, request_id=request_id, trace_id=trace_id)
            raise
        finally:
            csv_manager.cleanup(request_id)

    async def invoke_action(self, action_code: str, params: dict[str, object]) -> dict[str, object]:
        """执行动作，异常向上抛出。"""
        action = self._find_action(action_code)
        return await Action(action, loader=self._loader).execute(params)
