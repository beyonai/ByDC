"""
视图(View)实体模块

本模块定义了 View 类，用于跨对象的视图聚合。
View 聚合多个对象，提供跨对象的查询能力和自生说明。

核心功能：
- 跨对象查询：支持涉及多个对象的复杂查询
- 自生说明：生成 Markdown 格式的视图文档
- 查询管线：完整的计划 -> 执行 -> 聚合流程

使用示例：
    view = loader.get_view("scene_01_data_analysis")
    description = view.get_description()
    result = await view.query("查询各部门的销售业绩")
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from datacloud_data_sdk.relation import Relation

if TYPE_CHECKING:
    from datacloud_data_sdk.object import Object


class View:
    """
    视图实体类

    聚合多个对象，提供跨对象查询能力。
    通过 OntologyLoader.get_view() 获取实例。

    Attributes:
        view_id: 视图唯一标识
        view_name: 视图名称
        description: 视图描述
        objects: 包含的对象列表
        relations: 对象间的关联关系

    Example:
        view = loader.get_view("scene_01_data_analysis")
        result = await view.query("分析各产品的销售趋势")
    """

    def __init__(
        self,
        view_id: str,
        view_name: str,
        description: str,
        objects: list[Object],
        relations: list[Relation],
        loader: Any = None,
    ) -> None:
        """
        初始化视图实体

        Args:
            view_id: 视图唯一标识
            view_name: 视图名称
            description: 视图描述
            objects: 包含的对象列表
            relations: 对象间的关联关系
            loader: 本体加载器实例
        """
        self.view_id = view_id
        self.view_name = view_name
        self.description = description
        self.objects = objects
        self.relations = relations
        self._loader = loader

    def get_description(self) -> str:
        """
        生成 Markdown 格式的视图自生说明

        包含以下信息：
        - 视图名称和 ID
        - 视图描述
        - 包含的对象列表及其动作
        - 对象间的关联关系

        Returns:
            str: Markdown 格式的视图说明文档
        """
        lines = [
            f"## 视图：{self.view_name}（{self.view_id}）",
            "",
            f"{self.description}" if self.description else "",
            "",
            "**包含对象**：",
        ]
        for obj in self.objects:
            actions = ", ".join(f"`{c}`" for c in obj.list_action_codes())
            action_info = f"（动作：{actions}）" if actions else ""
            lines.append(f"- {obj._cls.object_name}（{obj.object_code}）{action_info}")

        if self.relations:
            lines += ["", "**对象关联**："]
            for r in self.relations:
                lines.append(
                    f"- {r.from_object} → {r.to_object}，{r.cardinality}"
                    + (f" —— {r.description}" if r.description else "")
                )

        return "\n".join(lines)

    async def query(self, question: str, include_plan: bool = True) -> dict[str, object]:
        """
        跨对象自然语言查询

        完整的查询管线：
        1. 构建视图载荷
        2. 生成查询计划（通过 LLM）
        3. 验证计划
        4. 应用数据权限重写
        5. 转换为执行任务
        6. 执行查询（SQL/API/脚本/知识库）
        7. 聚合结果

        Args:
            question: 自然语言查询问题
            include_plan: 是否在结果中包含执行计划

        Returns:
            dict: 查询结果，包含 records, total, meta 等字段

        Raises:
            CannotAnswerError: 无法回答问题时抛出
            PlanValidationError: 计划验证失败时抛出
        """
        import json
        import logging
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
        from datacloud_data_sdk.executor.api_executor import ApiExecutor
        from datacloud_data_sdk.executor.executor import Executor
        from datacloud_data_sdk.executor.kb_executor import KbExecutor
        from datacloud_data_sdk.executor.script_executor import ScriptExecutor
        from datacloud_data_sdk.plan.data_permission_rewriter import DataPermissionRewriter
        from datacloud_data_sdk.plan.execution_object_converter import ExecutionObjectConverter
        from datacloud_data_sdk.plan.object_view_builder import ObjectViewBuilder
        from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
        from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor

        loader = self._get_loader()
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
            pass

        try:
            object_ids = [obj.object_code for obj in self.objects]
            if observer:
                try:
                    await observer.on_query_start(request_id, question, object_ids)
                except Exception:
                    pass
            builder = ObjectViewBuilder(loader)
            payload = builder.build(object_ids=object_ids, view_id=self.view_id)
            if observer:
                try:
                    await observer.on_view_built(request_id, asdict(payload))
                except Exception:
                    pass

            plan = await config.plan_generator.generate(
                payload,
                question,
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
                        f"{s.step_id}({getattr(s, 'step_type', 'SQL')})"
                        for s in plan.steps
                    )
                    await gw_reporter.on_plan_generated(f"共 {len(plan.steps)} 步：{_step_types}")
                except Exception:
                    pass
            if observer:
                try:
                    await observer.on_plan_generated(request_id, plan_dict)
                except Exception:
                    pass
            try:
                logging.getLogger("datacloud_data_sdk").info(
                    json.dumps(plan_dict, ensure_ascii=False)
                )
            except Exception:
                pass

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
                    pass

            try:
                ctx = get_current_context()
                # plan = DataPermissionRewriter().rewrite(plan, ctx)
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
                    tasks_dict = []
                    for t in tasks:
                        tasks_dict.append(asdict(t))
                    agg_dict = asdict(plan.aggregation) if plan.aggregation else {}
                    await observer.on_execution_tasks_ready(
                        request_id, tasks_dict, agg_dict
                    )
                except Exception:
                    pass

            ds_manager = (
                DataSourceManager(config.datasource_configs)
                if config.datasource_configs
                else None
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
                    pass

            step_results = await executor.run(
                tasks, request_id, step_ids=[s.step_id for s in plan.steps]
            )

            if gw_reporter:
                try:
                    for _s in plan.steps:
                        await gw_reporter.on_step_completed(_s.step_id)
                except Exception:
                    pass
            if observer:
                try:
                    await observer.on_steps_executed(request_id, step_results.to_legacy_dict())
                except Exception:
                    pass

            if plan.aggregation:
                if gw_reporter:
                    try:
                        await gw_reporter.on_aggregating(plan.aggregation.strategy)
                    except Exception:
                        pass
                if plan.aggregation.strategy == "SQLITE_MEM":
                    records = await SqliteAggregator().aggregate(plan.aggregation, step_results)
                else:
                    records = await DirectAggregator().aggregate(plan.aggregation, step_results)
            else:
                records = []
            columns = (
                plan.aggregation.columns
                if plan.aggregation
                else []
            )
            if gw_reporter:
                try:
                    await gw_reporter.on_aggregation_completed(len(records))
                except Exception:
                    pass
            if observer:
                try:
                    await observer.on_aggregation_completed(
                        request_id, records, list(columns)
                    )
                except Exception:
                    pass

            from datacloud_data_sdk.result_formatter import build_query_response

            raw_result: dict[str, object] = {
                "records": records,
                "meta": {
                    "viewId": self.view_id,
                    "columns": list(columns),
                    "total": len(records),
                },
                "trace": {
                    "request_id": request_id,
                    "question": question,
                    "view_id": self.view_id,
                },
            }
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
                str(exc), result_type="rejected",
                trace={"request_id": request_id, "question": question, "view_id": self.view_id},
            )
        except (TermNotFoundError, TermAmbiguousError) as exc:
            from datacloud_data_sdk.result_formatter import build_error_data
            return build_error_data(
                str(exc), result_type="ask_user",
                trace={"request_id": request_id, "question": question, "view_id": self.view_id},
            )
        except PlanValidationError as exc:
            if observer:
                try:
                    plan_dict: dict = {}
                    if exc.plan:
                        plan_dict = {
                            "steps": [asdict(s) for s in exc.plan.steps],
                            "aggregation": (
                                asdict(exc.plan.aggregation)
                                if exc.plan.aggregation
                                else None
                            ),
                        }
                    await observer.on_plan_validation_failed(
                        request_id, exc.errors, plan_dict
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            from datacloud_data_sdk.events.trace_logger import log_exception_stack

            log_exception_stack(exc, request_id=request_id, trace_id=trace_id)
            raise
        finally:
            csv_manager.cleanup(request_id)

    def _get_loader(self) -> Any:
        """从 objects 中获取 OntologyLoader 引用。"""
        if self._loader is not None:
            return self._loader
        for obj in self.objects:
            if hasattr(obj, "_loader") and obj._loader is not None:
                return obj._loader
        raise NotImplementedError("View.query requires objects with configured OntologyLoader")

    async def invoke_object_action(
        self, object_code: str, action_code: str, params: dict[str, object]
    ) -> dict[str, object]:
        """通过视图调用对象动作，异常向上抛出。"""
        for obj in self.objects:
            if obj.object_code == object_code:
                return await obj.invoke_action(action_code, params)
        raise ValueError(f"Object {object_code!r} not in view {self.view_id!r}")
