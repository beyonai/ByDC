"""从本体定义动态生成 query_{code} / compute_{code} / action 工具。

工具命名约定（由 datacloud_data_service 工具生成器决定）：
- query_{object_code}   : DB/KB 对象查询工具（由 DynamicQueryToolGenerator 生成）
- compute_{object_code} : 聚合计算工具（对有 compute 动作的本体，由 ActionToolGenerator 生成）
- 其它动作工具由本体 OWL 定义决定命名
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部工具：JSON Schema → Pydantic BaseModel
# ---------------------------------------------------------------------------

def _schema_type_to_python(field_schema: dict[str, Any]) -> Any:
    """将 JSON Schema 字段类型映射到 Python 类型。复杂嵌套类型使用 dict / list。"""
    t = field_schema.get("type")
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        return list
    if t == "object":
        return dict
    # anyOf / oneOf / 无类型 → Any
    return Any


def _make_coerce_base(coerce_fields: frozenset[str]) -> type:
    """返回一个带 pre-validator 的 Pydantic BaseModel 基类。

    validator 将 dict/list 可选字段的空字符串 "" 转换为 None，
    防止 LLM 对这类字段传入 "" 而非 null/None。
    """
    from pydantic import BaseModel, model_validator  # noqa: PLC0415

    class _CoerceBase(BaseModel):
        @model_validator(mode="before")
        @classmethod
        def _coerce_empty_str_to_none(cls, values: Any) -> Any:
            if isinstance(values, dict):
                for fname in coerce_fields:
                    if fname in values and values[fname] == "":
                        values[fname] = None
            return values

    return _CoerceBase


def _json_schema_to_pydantic(schema: dict[str, Any], model_name: str) -> type:
    """
    将顶层为 object 的 JSON Schema 转换为简化的 Pydantic BaseModel。

    规则：
    - 顶层 properties → 对应 Python 类型字段
    - 嵌套 object / array → dict / list（携带 description）
    - required 字段 → 必填（无默认值）；其余字段 → Optional，默认 None
    - schema 为空或非 object 类型 → 生成空 BaseModel（接受任意调用）
    - 可选的 dict/list 字段：描述中注明期望类型，并在 pre-validator 中将 "" 转换为
      None（防止 LLM 用空字符串代替 null）
    """
    from pydantic import BaseModel, Field, create_model  # noqa: PLC0415

    if not isinstance(schema, dict) or schema.get("type") != "object":
        return create_model(model_name, __base__=BaseModel)

    properties: dict[str, Any] = schema.get("properties", {})
    required_fields: set[str] = set(schema.get("required", []))
    pydantic_fields: dict[str, Any] = {}
    # 记录需要空字符串转 None 的可选 dict/list 字段
    coerce_fields: set[str] = set()

    _TYPE_LABEL: dict[type, str] = {dict: "object", list: "array"}

    for field_name, field_schema in properties.items():
        py_type = _schema_type_to_python(field_schema)
        description = field_schema.get("description", field_name)

        if field_name in required_fields:
            pydantic_fields[field_name] = (py_type, Field(..., description=description))
        else:
            # 为 dict/list 类型追加类型说明，提示 LLM 不需要时传 null 而非 ""
            if py_type in _TYPE_LABEL:
                description = f"{description}（{_TYPE_LABEL[py_type]}，不需要时传 null 或省略）"
                coerce_fields.add(field_name)
            pydantic_fields[field_name] = (
                Optional[py_type],
                Field(default=None, description=description),
            )

    base = _make_coerce_base(frozenset(coerce_fields)) if coerce_fields else BaseModel
    return create_model(model_name, __base__=base, **pydantic_fields)


# ---------------------------------------------------------------------------
# 内部工具：执行闭包
# ---------------------------------------------------------------------------

def _make_tool_coroutine(ont_action: Any, loader: Any) -> Any:
    """创建工具的异步执行闭包，通过 Action(ont_action, loader).execute(kwargs) 运行。"""

    async def _execute(**kwargs: Any) -> Any:
        try:
            from datacloud_data_sdk.action import Action  # noqa: PLC0415

            action = Action(ont_action, loader)
            return await action.execute(kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("OntologyToolLoader: 工具执行失败: %s", exc, exc_info=True)
            return {"error": str(exc)}

    return _execute


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class OntologyToolLoader:
    """
    根据 mounted_objects 列表，从 datacloud_data_service 的工具生成器
    生成对应的 LangChain StructuredTool 字典。

    调用示例::

        from datacloud_data_sdk.ontology.loader import OntologyLoader
        loader = OntologyLoader()
        loader.load_scene_from_path(scene_path)

        tools = OntologyToolLoader(
            mounted_objects=["Order", "CustomerView"],
            loader=loader,
        ).load()
        # tools == {
        #   "query_Order":       StructuredTool(...),
        #   "query_CustomerView": StructuredTool(...),
        #   "Order_create":      StructuredTool(...),
        #   ...
        # }

    注意：
    - 若 ``mounted_objects`` 为空或 ``loader`` 未提供，返回空字典（不报错）。
    - 若 ``datacloud_data_service`` 未安装，记录 warning 并返回空字典。
    - 同名工具只生成一次；caller 传入的 ``tools`` 参数可在 ``create_agent`` 层覆盖。
    """

    def __init__(
        self,
        mounted_objects: list[str] | None = None,
        loader: Any | None = None,
    ) -> None:
        self._mounted_objects = mounted_objects or []
        self._loader = loader

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """
        加载所有挂载对象的 LangChain 工具。

        Returns:
            dict[str, StructuredTool]: key 为工具名，value 为 StructuredTool 实例。
        """
        if not self._mounted_objects:
            return {}

        if self._loader is None:
            logger.debug(
                "OntologyToolLoader: loader 未提供，跳过本体工具生成 "
                "(mounted_objects=%s)",
                self._mounted_objects,
            )
            return {}

        try:
            from datacloud_data_service.tools.dynamic_query_tool_generator import (  # noqa: PLC0415
                DynamicQueryToolGenerator,
            )
            from datacloud_data_service.tools.action_tool_generator import (  # noqa: PLC0415
                ActionToolGenerator,
            )
        except ImportError as exc:
            logger.warning(
                "OntologyToolLoader: datacloud_data_service 未安装，"
                "跳过本体工具生成: %s",
                exc,
            )
            return {}

        query_gen = DynamicQueryToolGenerator(self._loader)
        action_gen = ActionToolGenerator(self._loader)
        tools: dict[str, Any] = {}

        for obj_code in self._mounted_objects:
            # 1. query_{code} 虚拟查询工具
            query_tool = self._build_query_tool(query_gen, obj_code)
            if query_tool is not None:
                tools[query_tool.name] = query_tool

            # 2. 本体动作工具（含 compute 类型）
            action_tools = self._build_action_tools(action_gen, obj_code)
            tools.update(action_tools)

        logger.info(
            "OntologyToolLoader: 已生成 %d 个本体工具: %s",
            len(tools),
            sorted(tools.keys()),
        )
        return tools

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _build_query_tool(self, query_gen: Any, obj_code: str) -> Any | None:
        """为对象生成 query_{code} 工具（虚拟查询动作）。"""
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            tool_def = query_gen.generate(obj_code)
            if tool_def is None:
                logger.debug(
                    "OntologyToolLoader: %s 不是 DB/KB 类型，跳过 query 工具生成", obj_code
                )
                return None

            ont_action = query_gen.generate_ontology_action(obj_code)
            if ont_action is None:
                logger.warning(
                    "OntologyToolLoader: generate_ontology_action(%s) 返回 None，跳过", obj_code
                )
                return None

            return StructuredTool(
                name=tool_def["name"],
                description=tool_def.get("description", tool_def["name"]),
                args_schema=_json_schema_to_pydantic(
                    tool_def.get("inputSchema", {}),
                    f"_Query{obj_code}Schema",
                ),
                coroutine=_make_tool_coroutine(ont_action, self._loader),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OntologyToolLoader: 构建 query_%s 工具失败: %s", obj_code, exc)
            return None

    def _build_action_tools(self, action_gen: Any, obj_code: str) -> dict[str, Any]:
        """为本体下定义的动作生成 LangChain 工具（含 compute 类型动作）。"""
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            for tool_def in action_gen.generate_tools(obj_code):
                name: str = tool_def.get("name", "")
                if not name:
                    continue
                try:
                    meta = tool_def.get("_meta", {})
                    action_code: str = meta.get("action_type") or meta.get("action_code", "")
                    ont_action = self._loader.get_action(obj_code, action_code)
                    result[name] = StructuredTool(
                        name=name,
                        description=tool_def.get("description", name),
                        args_schema=_json_schema_to_pydantic(
                            tool_def.get("inputSchema", {}),
                            f"_{name}_Schema",
                        ),
                        coroutine=_make_tool_coroutine(ont_action, self._loader),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "OntologyToolLoader: 构建 %s 的动作工具 %s 失败: %s",
                        obj_code,
                        name,
                        exc,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OntologyToolLoader: ActionToolGenerator.generate_tools(%s) 失败: %s",
                obj_code,
                exc,
            )
        return result
