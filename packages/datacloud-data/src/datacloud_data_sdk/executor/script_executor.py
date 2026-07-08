"""
脚本执行器模块

本模块提供 Python 脚本的执行能力，用于执行与动作绑定的脚本代码。
脚本在沙箱环境中执行，注入与调试环境完全相同的命名空间：

    Q  — QueryWrapper 工厂（链式条件构造器）
    A  — AggWrapper 工厂（链式聚合构造器）
    {entity_code}_mapper — ProductionMapper 实例（通过 OntologyLoader 操作真实数据源）
    {EntityClass}        — 实体 dataclass（带 F 内部类，字段与调试环境一致）
    params               — Action 入参 dict
    context              — RequestContext（当前请求上下文）
    loader               — OntologyLoader（本体加载器，可选）
    httpx                — HTTP 客户端模块（如果已安装）

脚本约定：
- 必须定义 `def execute(params: dict) -> dict` 函数
- 函数接收参数字典，返回结果字典

使用示例：
    executor = ScriptExecutor(ontology_loader)
    result = await executor.execute(script_code, {"param1": "value1"})
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import ScriptExecutionError
from datacloud_data_sdk.wrappers import AggWrapper, QueryWrapper

logger = logging.getLogger(__name__)


def _to_class_name(entity_code: str) -> str:
    return "".join(part.capitalize() for part in entity_code.split("_"))


def _build_entity_class_from_ontology(cls: Any) -> type:
    """从 OntologyClass 动态构建带 F 内部类的实体 class（与 DebugLoader 逻辑对齐）。"""
    annotations: dict[str, Any] = {"id": "int | None"}
    defaults: dict[str, Any] = {"id": None}
    f_attrs: dict[str, str] = {"id": "id"}

    for field in getattr(cls, "fields", []):
        code = getattr(field, "field_code", "")
        if not code or code.lower() == "id":
            continue
        annotations[code] = "Any | None"
        defaults[code] = None
        f_attrs[code] = code

    f_class = type("F", (), {**f_attrs})

    def __init__(self: Any, **kwargs: Any) -> None:  # noqa: N807
        for key, default in defaults.items():
            setattr(self, key, kwargs.get(key, default))

    def to_dict(self: Any) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None and not k.startswith("_")}

    cls_attrs: dict[str, Any] = {
        "__annotations__": annotations,
        "__init__": __init__,
        "to_dict": to_dict,
        "F": f_class,
        **defaults,
    }
    return type(_to_class_name(cls.object_code), (), cls_attrs)


def _build_production_mapper(object_code: str, entity_cls: type, loader: Any) -> Any:
    """构建生产环境 Mapper，通过 OntologyLoader 操作真实数据源。

    方法签名与 DebugMapper 完全一致，Action 脚本无需区分环境。
    """

    class ProductionMapper:
        def __init__(self) -> None:
            self._object_code = object_code
            self._entity_cls = entity_cls
            self._loader = loader

        def _get_dq_executor(self) -> Any:
            from datacloud_data_sdk.executor.dynamic_query_executor import DynamicQueryExecutor

            return DynamicQueryExecutor(self._loader)

        def _get_dt_executor(self) -> Any:
            from datacloud_data_sdk.executor.dynamic_table_executor import DynamicTableExecutor

            return DynamicTableExecutor(self._loader)

        def _q_to_args(self, q: QueryWrapper) -> dict[str, Any]:
            """QueryWrapper → DynamicQueryExecutor arguments dict。"""
            args: dict[str, Any] = {"filters": q.to_filters()}
            if q._limit_n is not None:
                args["limit"] = q._limit_n
            elif q._page_size is not None:
                args["limit"] = q._page_size
                args["offset"] = (q._page_num - 1) * q._page_size
            if q._order_fields:
                args["order_by"] = [
                    {"field": f, "direction": "DESC" if desc else "ASC"}
                    for f, desc in q._order_fields
                ]
            return args

        def _a_to_args(self, a: AggWrapper) -> dict[str, Any]:
            """AggWrapper → DynamicQueryExecutor arguments dict。"""
            args: dict[str, Any] = {
                "aggregates": a._aggregates,
                "group_by": a._group_fields,
            }
            if a._where_wrapper is not None:
                args["filters"] = a._where_wrapper.to_filters()
            if a._limit_n is not None:
                args["limit"] = a._limit_n
            if a._order_fields:
                args["order_by"] = [
                    {"field": f, "direction": "DESC" if desc else "ASC"}
                    for f, desc in a._order_fields
                ]
            return args

        def _row_to_entity(self, row: dict[str, Any]) -> Any:
            return self._entity_cls(**row)

        async def select(self, q: QueryWrapper) -> dict[str, Any]:
            """条件查询，返回 {records, total, meta}。"""
            executor = self._get_dq_executor()
            return await executor.execute(self._object_code, self._q_to_args(q))

        async def select_one(self, q: QueryWrapper) -> Any:
            """条件查询第一条，返回实体或 None。"""
            args = self._q_to_args(q)
            args["limit"] = 1
            executor = self._get_dq_executor()
            result = await executor.execute(self._object_code, args)
            records: list[dict[str, Any]] = result.get("records", [])
            return self._row_to_entity(records[0]) if records else None

        async def count(self, q: QueryWrapper) -> int:
            """条件计数。"""
            executor = self._get_dq_executor()
            result = await executor.execute(self._object_code, self._q_to_args(q))
            return int(result.get("total", 0))

        async def agg(self, a: AggWrapper) -> dict[str, Any]:
            """聚合查询，返回 {records, total, meta}。"""
            executor = self._get_dq_executor()
            return await executor.execute(self._object_code, self._a_to_args(a))

        async def select_by_id(self, id: int) -> Any:
            """按主键查询单条。"""
            return await self.select_one(QueryWrapper().eq("id", id))

        async def insert(self, obj: Any) -> Any:
            """插入记录，返回含自增 id 的实体。"""
            executor = self._get_dt_executor()
            result = await executor.insert(self._object_code, {"records": [obj.to_dict()]})
            records: list[dict[str, Any]] = result.get("records", [])
            if records:
                obj.id = records[0].get("id", obj.id)
            await self._enqueue_sync("insert", [obj.to_dict()])
            return obj

        async def update_by_id(self, obj: Any) -> bool:
            """按 id 更新记录。"""
            data = obj.to_dict()
            id_val = data.pop("id", None)
            if not id_val or not data:
                return False
            executor = self._get_dt_executor()
            result = await executor.update(
                self._object_code,
                {
                    "values": data,
                    "filters": {"id": {"op": "eq", "value": id_val}},
                },
            )
            ok = bool(result.get("records") or result.get("affected", 0))
            if ok:
                full = dict(data)
                full["id"] = id_val
                await self._enqueue_sync("update", [full])
            return ok

        async def delete_by_id(self, id: int) -> bool:
            """按主键删除。"""
            # 先读快照再删除，保证 term_code 可从记录中提取
            snapshot = await self.select_by_id(id)
            executor = self._get_dt_executor()
            result = await executor.delete(
                self._object_code, {"filters": {"id": {"op": "eq", "value": id}}}
            )
            ok = bool(result.get("affected", 0))
            if ok and snapshot is not None:
                await self._enqueue_sync("delete", [snapshot.to_dict()])
            return ok

        async def _enqueue_sync(self, op: str, records: list[dict[str, Any]]) -> None:
            """非阻塞投递术语同步事件。"""
            ontology_cls = self._loader.get_class(self._object_code)
            if ontology_cls is None:
                return
            cfg = getattr(ontology_cls, "term_sync", None)
            if cfg is None or not cfg.enabled or op not in cfg.sync_on:
                return
            try:
                from datacloud_knowledge.sync import (  # type: ignore[import-untyped]
                    TermSyncEvent,
                    enqueue_sync,
                )

                await enqueue_sync(
                    TermSyncEvent(
                        op=op,
                        object_code=self._object_code,
                        records=records,
                        config=cfg,
                    )
                )
            except Exception:
                pass  # knowledge 包不可用时静默跳过

    mapper = ProductionMapper()
    mapper.__class__.__name__ = f"{_to_class_name(object_code)}Mapper"
    return mapper


class ScriptExecutor:
    """
    脚本执行器

    执行预定义的 Python 脚本代码，注入与调试环境完全相同的命名空间。
    调试环境（DebugLoader + SQLite）与正式执行（ProductionMapper + 真实数据源）
    的 mapper 方法签名完全一致，脚本无需区分执行模式。

    Attributes:
        _loader: 本体加载器引用，可注入到脚本环境中

    Example:
        executor = ScriptExecutor(loader)
        result = await executor.execute(
            "async def execute(params): ...",
            {"x": 5}
        )
    """

    def __init__(self, ontology_loader: Any = None) -> None:
        self._loader = ontology_loader

    async def execute(
        self,
        script: str,
        params: dict[str, Any],
        action_code: str = "<inline>",
        timeout: float = 30.0,
        extra_namespace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        编译并执行脚本，注入完整命名空间。

        Args:
            script: Python 脚本代码
            params: 传递给 execute 函数的参数
            action_code: 动作代码，用于错误信息
            timeout: 执行超时时间（秒）
            extra_namespace: 额外注入的命名空间，会覆盖默认注入的 mapper/实体类
                             调试环境用此参数注入 DebugMapper，从而与正式执行共享同一套脚本执行逻辑

        Returns:
            dict: execute 函数返回的结果字典

        Raises:
            ScriptExecutionError: 脚本语法错误、执行错误或超时时抛出
        """
        try:
            ctx = get_current_context()
        except Exception:
            ctx = None

        namespace: dict[str, Any] = {
            "context": ctx,
            "loader": self._loader,
            "Q": QueryWrapper(),
            "A": AggWrapper(),
            "params": params,
        }

        try:
            import httpx

            namespace["httpx"] = httpx
        except ImportError:
            pass

        # 从 loader 中为每个对象注入实体类和 mapper（extra_namespace 未覆盖时才注入）
        if self._loader is not None and not extra_namespace:
            try:
                all_classes = self._loader.get_ontology_classes()
                for ontology_cls in all_classes:
                    entity_code = ontology_cls.object_code
                    entity_cls = _build_entity_class_from_ontology(ontology_cls)
                    mapper = _build_production_mapper(entity_code, entity_cls, self._loader)
                    namespace[f"{entity_code}_mapper"] = mapper
                    namespace[_to_class_name(entity_code)] = entity_cls
            except Exception:
                pass  # loader 不支持 list 时退化，不影响 script 运行

        # extra_namespace 最后写入，允许调试环境用 DebugMapper 覆盖默认 mapper
        if extra_namespace:
            namespace.update(extra_namespace)

        try:
            exec(compile(script, f"<action:{action_code}>", "exec"), namespace)  # noqa: S102
        except SyntaxError as e:
            raise ScriptExecutionError(action_code, f"SyntaxError: {e}", line_no=e.lineno)

        execute_fn = namespace.get("execute")
        if execute_fn is None or not callable(execute_fn):
            raise ScriptExecutionError(
                action_code,
                "Script must define `def execute(params: dict) -> dict`",
            )

        import inspect

        loop = asyncio.get_event_loop()
        try:
            if inspect.iscoroutinefunction(execute_fn):
                result = await asyncio.wait_for(
                    execute_fn(params),
                    timeout=timeout,
                )
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, execute_fn, params),
                    timeout=timeout,
                )
        except TimeoutError:
            raise ScriptExecutionError(action_code, f"Script timed out after {timeout}s")
        except ScriptExecutionError:
            raise
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            line_no = tb[-1].lineno if tb else None
            logger.error(
                "脚本执行失败 action=%s line=%s\n%s",
                action_code,
                line_no,
                traceback.format_exc(),
            )
            raise ScriptExecutionError(action_code, str(e), line_no=line_no)

        if not isinstance(result, dict):
            raise ScriptExecutionError(
                action_code,
                f"execute() must return dict, got {type(result).__name__}",
            )
        return result
