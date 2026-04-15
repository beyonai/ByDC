"""从本体定义动态生成 query_{code} / compute_{code} / action 工具。

架构说明（统一以 MCP Server / ToolRegistry 为标准）：
- OBJECT 类型：经 inject_virtual_actions 注入后，通过 ActionToolGenerator 读取 cls.actions 生成工具
  执行路径：ActionExecutor.execute(obj_code, action_code, args)
- VIEW 类型：直接读取 view.actions 生成工具
  执行路径：view.invoke_action(action_code, args)
- 降级兜底：若 inject_virtual_actions 未调用（cls.actions 为空），退回 DynamicQueryToolGenerator

工具命名约定（由 datacloud_data_service 工具生成器决定）：
- query_{object_code}   : DB/KB 对象查询工具（由 inject_virtual_actions 注入）
- compute_{object_code} : 聚合计算工具（由 inject_virtual_actions 注入）
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
    """将 JSON Schema 字段类型映射到 Python 类型。

    array 类型会检查 items 子 schema：
    - items.type == "string" → list[str]（保留 items 信息，防止 LLM 填 dict/object）
    - 其他 array → list
    """
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
        items = field_schema.get("items")
        if isinstance(items, dict) and items.get("type") == "string":
            return list[str]  # Pydantic 会生成 items:{type:string}，LLM 知道元素是字符串
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


def _get_array_label(py_type: Any) -> str:
    """返回 array 类型的描述标签（用于拼接到 description 里告知 LLM 元素格式）。"""
    import typing  # noqa: PLC0415
    origin = getattr(py_type, "__origin__", None)
    if origin is list:
        args = getattr(py_type, "__args__", ())
        if args and args[0] is str:
            return "string 数组（每个元素为字段名字符串，如 [\"字段A\", \"字段B\"]）"
        return "array"
    return "array"


def _json_schema_to_pydantic(schema: dict[str, Any], model_name: str) -> type:
    """
    将顶层为 object 的 JSON Schema 转换为简化的 Pydantic BaseModel。

    规则：
    - 顶层 properties → 对应 Python 类型字段
    - array[string] → list[str]（携带 items 信息，LLM 看到 items:{type:string}）
    - 其他 array / object → list / dict（携带 description）
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

    for field_name, field_schema in properties.items():
        py_type = _schema_type_to_python(field_schema)
        description = field_schema.get("description", field_name)

        # 判断是否为 list/dict 类族（含泛型 list[str] 等）
        origin = getattr(py_type, "__origin__", None)
        is_list_like = py_type is list or origin is list
        is_dict_like = py_type is dict or origin is dict

        if field_name in required_fields:
            pydantic_fields[field_name] = (py_type, Field(..., description=description))
        else:
            # 为 dict/list 类型追加类型说明，提示 LLM 不需要时传 null 而非 ""
            if is_list_like:
                label = _get_array_label(py_type)
                description = f"{description}（{label}，不需要时传 null 或省略）"
                coerce_fields.add(field_name)
            elif is_dict_like:
                description = f"{description}（object，不需要时传 null 或省略）"
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
    """降级兜底执行闭包：通过 Action(ont_action, loader).execute(kwargs) 运行。

    仅在 inject_virtual_actions 未调用（_build_query_tool fallback）时使用。
    """

    async def _execute(**kwargs: Any) -> Any:
        try:
            from datacloud_data_sdk.action import Action  # noqa: PLC0415

            action = Action(ont_action, loader)
            return await action.execute(kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("OntologyToolLoader: 工具执行失败: %s", exc, exc_info=True)
            return {"error": str(exc)}

    return _execute


def _make_object_action_coroutine(obj_code: str, action_code: str, loader: Any) -> Any:
    """OBJECT 工具执行闭包：通过 ActionExecutor 路由，与 MCP call_tool 对象分支对齐。"""

    async def _execute(**kwargs: Any) -> Any:
        try:
            from datacloud_data_service.tools.action_executor import (  # noqa: PLC0415
                ActionExecutor,
            )

            executor = ActionExecutor(loader)
            return await executor.execute(obj_code, action_code, kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "OntologyToolLoader: OBJECT 工具执行失败 (%s/%s): %s",
                obj_code,
                action_code,
                exc,
                exc_info=True,
            )
            return {"error": str(exc)}

    return _execute


def _make_view_action_coroutine(view_code: str, action_code: str, loader: Any) -> Any:
    """VIEW 工具执行闭包：通过 view.invoke_action()，与 MCP call_tool VIEW 分支对齐。"""

    async def _execute(**kwargs: Any) -> Any:
        try:
            view = loader.get_view(view_code)
            return await view.invoke_action(action_code, kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "OntologyToolLoader: VIEW 工具执行失败 (%s/%s): %s",
                view_code,
                action_code,
                exc,
                exc_info=True,
            )
            return {"error": str(exc)}

    return _execute


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------


class OntologyToolLoader:
    """
    根据 mounted_objects 列表，从 datacloud_data_service 的工具生成器
    生成对应的 LangChain StructuredTool 字典。

    执行路径（统一对齐 MCP Server / ToolRegistry）：
    - OBJECT：ActionToolGenerator 读取 inject_virtual_actions 后的 cls.actions
              → ActionExecutor.execute(obj_code, action_code, args)
    - VIEW：  view.actions 直接生成工具
              → view.invoke_action(action_code, args)
    - 降级兜底：inject_virtual_actions 未调用时退回 DynamicQueryToolGenerator

    参数：
        mounted_objects:      需挂载的本体对象/视图 code 列表
        loader:               OntologyLoader 实例（需已调用 load_from_owl_directory
                              及 inject_virtual_actions）
        skip_action_families: 需跳过的 action_type 族集合。
                              db_query 模式下传 frozenset({"query", "compute"}) 以
                              跳过虚拟注入动作，只保留 OWL 原生自定义 action。

    调用示例::

        from datacloud_data_sdk.ontology.loader import OntologyLoader
        from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

        loader = OntologyLoader()
        loader.load_from_owl_directory(scene_path)
        inject_virtual_actions(loader)   # 必须在此之前调用

        tools = OntologyToolLoader(
            mounted_objects=["ads_chain_analysis", "scene_enterprise_analysis"],
            loader=loader,
        ).load()

    注意：
    - 若 ``mounted_objects`` 为空或 ``loader`` 未提供，返回空字典（不报错）。
    - 若 ``datacloud_data_service`` 未安装，记录 warning 并返回空字典。
    - 同名工具只生成一次；caller 传入的 ``tools`` 参数可在 ``create_agent`` 层覆盖。
    """

    def __init__(
        self,
        mounted_objects: list[str] | None = None,
        loader: Any | None = None,
        skip_action_families: frozenset[str] = frozenset(),
    ) -> None:
        self._mounted_objects = mounted_objects or []
        self._loader = loader
        self._skip_action_families = skip_action_families

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
            if self._is_view(obj_code):
                # VIEW 类型：直接读取 view.actions，对齐 ToolRegistry._append_view_tools
                view_tools = self._build_view_tools(obj_code)
                tools.update(view_tools)
            else:
                # OBJECT 类型：优先通过 ActionToolGenerator 生成所有动作工具
                # 前提：_build_shared_loader 已调用 inject_virtual_actions
                action_tools = self._build_action_tools(action_gen, obj_code)
                tools.update(action_tools)

                # 降级兜底：若未产出 query 族工具且未要求跳过，尝试 DynamicQueryToolGenerator
                # 场景：inject_virtual_actions 未调用（旧环境或直接调用方跳过了注入）
                if (
                    "query" not in self._skip_action_families
                    and not any(
                        k.startswith(f"query_{obj_code}") for k in action_tools
                    )
                ):
                    query_tool = self._build_query_tool(query_gen, obj_code)
                    if query_tool is not None:
                        tools[query_tool.name] = query_tool

        logger.info(
            "OntologyToolLoader: 已生成 %d 个本体工具: %s",
            len(tools),
            sorted(tools.keys()),
        )
        return tools

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _is_view(self, code: str) -> bool:
        """检查 code 是否为 VIEW 类型（在 loader._scenes 中）。"""
        scenes = getattr(self._loader, "_scenes", {})
        return code in scenes

    def _build_view_tools(self, view_code: str) -> dict[str, Any]:
        """为 VIEW 类型生成工具，对齐 ToolRegistry._append_view_tools 逻辑。"""
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            view = self._loader.get_view(view_code)
            for action in view.actions:
                # 跳过 skip_action_families 中的族（db_query 模式跳过 query/compute）
                if getattr(action, "action_type", "") in self._skip_action_families:
                    continue
                exposure = getattr(action, "exposure_policy", "direct")
                if exposure == "hidden":
                    continue
                if not action.input_schema:
                    continue
                result[action.action_code] = StructuredTool(
                    name=action.action_code,
                    description=action.description or action.action_name,
                    args_schema=_json_schema_to_pydantic(
                        action.input_schema,
                        f"_{action.action_code}_Schema",
                    ),
                    coroutine=_make_view_action_coroutine(
                        view_code, action.action_code, self._loader
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OntologyToolLoader: 构建 VIEW %s 工具失败: %s", view_code, exc
            )
        return result

    def _build_action_tools(self, action_gen: Any, obj_code: str) -> dict[str, Any]:
        """为 OBJECT 生成动作工具（含 query / compute / OWL 自定义）。

        执行路径对齐 MCP call_tool 对象分支：ActionExecutor.execute(obj_code, action_code, args)。
        需要 inject_virtual_actions 已在 loader 上调用，否则 cls.actions 为空，返回 {}。
        """
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            for tool_def in action_gen.generate_tools(obj_code):
                name: str = tool_def.get("name", "")
                if not name:
                    continue

                meta = tool_def.get("_meta", {})
                action_family: str = meta.get("action_type", "")

                # 跳过需要排除的族（db_query 模式下跳过 query / compute 虚拟注入动作）
                if action_family in self._skip_action_families:
                    continue

                # 优先使用 _meta["action_code"]（唯一码，由 action_tool_generator 写入）
                # fallback 到工具名 name：ActionToolGenerator 保证 name == action.action_code
                # 不能 fallback 到 action_family（族名如 "query"），那只是类型标签，不是唯一码
                action_code: str = meta.get("action_code") or name

                try:
                    result[name] = StructuredTool(
                        name=name,
                        description=tool_def.get("description", name),
                        args_schema=_json_schema_to_pydantic(
                            tool_def.get("inputSchema", {}),
                            f"_{name}_Schema",
                        ),
                        coroutine=_make_object_action_coroutine(
                            obj_code, action_code, self._loader
                        ),
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

    def _build_query_tool(self, query_gen: Any, obj_code: str) -> Any | None:
        """降级兜底：为对象生成 query_{code} 工具（inject_virtual_actions 未调用时使用）。

        正常路径（inject_virtual_actions 已调用）不走此处，通过 _build_action_tools 覆盖。
        """
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            tool_def = query_gen.generate(obj_code)
            if tool_def is None:
                logger.debug(
                    "OntologyToolLoader: %s 不是 DB/KB 类型，跳过 query 工具降级生成",
                    obj_code,
                )
                return None

            ont_action = query_gen.generate_ontology_action(obj_code)
            if ont_action is None:
                logger.warning(
                    "OntologyToolLoader: generate_ontology_action(%s) 返回 None，跳过",
                    obj_code,
                )
                return None

            logger.debug(
                "OntologyToolLoader: FALLBACK — 使用 DynamicQueryToolGenerator 为 %s 生成 query 工具"
                "（请确认 inject_virtual_actions 已在 _build_shared_loader 中调用）",
                obj_code,
            )
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
            logger.warning(
                "OntologyToolLoader: 构建 query_%s 工具失败: %s", obj_code, exc
            )
            return None
