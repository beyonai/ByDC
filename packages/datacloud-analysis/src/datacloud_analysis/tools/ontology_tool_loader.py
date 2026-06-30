"""从本体定义动态生成 query_{code} / compute_{code} / action 工具。

架构说明（统一以 MCP Server / ToolRegistry 为标准）：
- OBJECT 类型：经 inject_virtual_actions 注入后，通过 ActionToolGenerator 读取 cls.actions 生成工具
  执行路径：ActionExecutor.execute(obj_code, action_code, args)
- 非 DB OBJECT 类型：直接读取对象动作 schema 生成工具
  执行路径：ActionExecutor.execute(obj_code, action_code, args)
- VIEW 类型：直接读取 view.actions 生成工具
  执行路径：view.invoke_action(action_code, args)
- 降级兜底：若 inject_virtual_actions 未调用（cls.actions 为空），退回 DynamicQueryToolGenerator

工具命名约定（由平台工具生成器决定）：
- query_{object_code}   : DB/KB 对象查询工具（由 inject_virtual_actions 注入）
- compute_{object_code} : 聚合计算工具（由 inject_virtual_actions 注入）
- 其它动作工具由本体 OWL 定义决定命名
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from datacloud_platform.config import get_settings

logger = logging.getLogger(__name__)

# ── 平台路由 ──────────────────────────────────────────────────────────────────
from datacloud_platform import get_platform  # noqa: E402

_base_id = get_platform()._default_base_id()  # fixme: pass base_id explicitly

# ---------------------------------------------------------------------------
# 哨兵对象：区分"未传 loader"与"显式传 loader=None"
# ---------------------------------------------------------------------------

_LOADER_NOT_PROVIDED: object = object()

# ---------------------------------------------------------------------------
# 动态 Pydantic 类注册表：防止 dill PicklingError
# 同名类只创建一次；后续调用直接返回缓存实例，保证 id() 不变。
# ---------------------------------------------------------------------------

_DYNAMIC_SCHEMA_REGISTRY: dict[str, type] = {}


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

    origin = getattr(py_type, "__origin__", None)
    if origin is list:
        args = getattr(py_type, "__args__", ())
        if args and args[0] is str:
            return 'string 数组（每个元素为字段名字符串，如 ["字段A", "字段B"]）'
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

    if model_name in _DYNAMIC_SCHEMA_REGISTRY:
        return _DYNAMIC_SCHEMA_REGISTRY[model_name]

    if not isinstance(schema, dict) or schema.get("type") != "object":
        _m = create_model(model_name, __base__=BaseModel)
        _m.__module__ = __name__
        setattr(sys.modules[__name__], model_name, _m)
        _DYNAMIC_SCHEMA_REGISTRY[model_name] = _m
        return _m

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

        # 透传 array 类字段的长度约束到 Pydantic Field（→ JSON Schema minItems/maxItems），
        # 避免源 schema 中的 minItems/maxItems 在转换过程中被静默丢弃。
        list_constraints: dict[str, int] = {}
        if is_list_like:
            min_items = field_schema.get("minItems")
            max_items = field_schema.get("maxItems")
            if isinstance(min_items, int):
                list_constraints["min_length"] = min_items
            if isinstance(max_items, int):
                list_constraints["max_length"] = max_items
        json_schema_extra: dict[str, Any] = {}
        if is_list_like and isinstance(field_schema.get("items"), dict):
            json_schema_extra["items"] = field_schema["items"]

        if field_name in required_fields:
            pydantic_fields[field_name] = (
                py_type,
                Field(
                    ...,
                    description=description,
                    json_schema_extra=json_schema_extra or None,
                    **list_constraints,
                ),
            )
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
                py_type | None,
                Field(
                    default=None,
                    description=description,
                    json_schema_extra=json_schema_extra or None,
                    **list_constraints,
                ),
            )

    base = _make_coerce_base(frozenset(coerce_fields)) if coerce_fields else BaseModel
    _m = create_model(model_name, __base__=base, **pydantic_fields)
    _m.__module__ = __name__
    setattr(sys.modules[__name__], model_name, _m)
    _DYNAMIC_SCHEMA_REGISTRY[model_name] = _m
    return _m


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
        logger.warning(
            "[_make_object_action_coroutine] obj=%s action=%s kwargs_keys=%s metrics_raw=%r metrics_type=%s",
            obj_code,
            action_code,
            sorted(kwargs.keys()),
            kwargs.get("metrics"),
            type(kwargs.get("metrics")).__name__,
        )
        try:
            from datacloud_platform import get_platform  # noqa: PLC0415

            return await get_platform().execute_action(
                _base_id, loader, obj_code, action_code, kwargs
            )
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
        logger.info(
            "[_make_view_action_coroutine] view=%s action=%s kwargs_keys=%s"
            " dimensions=%s metrics=%s",
            view_code,
            action_code,
            sorted(kwargs.keys()),
            kwargs.get("dimensions"),
            kwargs.get("metrics"),
        )
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
    根据 mounted_objects 列表，从平台工具生成器
    生成对应的 LangChain StructuredTool 字典。

    执行路径（统一对齐 MCP Server / ToolRegistry）：
    - DB OBJECT：ActionToolGenerator 读取 inject_virtual_actions 后的 cls.actions
                 → ActionExecutor.execute(obj_code, action_code, args)
    - 非 DB OBJECT：object.get_action_schema(action_code) 直接生成工具
                    → ActionExecutor.execute(obj_code, action_code, args)
    - VIEW：       view.actions 直接生成工具
                    → view.invoke_action(action_code, args)
    - 降级兜底：DB OBJECT 在 inject_virtual_actions 未调用时退回 DynamicQueryToolGenerator

    参数：
        mounted_objects:      需挂载的本体对象/视图 code 列表
        loader:               OntologyLoader 实例（需已调用 load_from_owl_directory
                              及 inject_virtual_actions）。与 ontology_path 互斥，
                              优先级更高。显式传 None 时保持旧行为（skip + debug log）。
        ontology_path:        OWL 文件目录路径。传入时由 OntologyToolLoader 内部自动
                              调用 load_from_owl_directory + inject_virtual_actions，
                              无需外部构建 loader。与 loader 互斥。
        skip_action_families: 需跳过的 action_type 族集合。
                              db_query 模式下传 frozenset({"query", "compute"}) 以
                              跳过虚拟注入动作，只保留 OWL 原生自定义 action。
        agent_friendly:       True（默认）时对 query/compute 工具的 schema 做全量修正，
                              使 LLM 感知字段中文名可用，并覆写 complex_conditions 描述。

    调用示例（新接口，agent 侧）::

        tools = OntologyToolLoader(
            mounted_objects=["enterprise", "manage_grid"],
            ontology_path="/path/to/owl",
        ).load()

    调用示例::

        tools = OntologyToolLoader(
            mounted_objects=["enterprise"],
            loader=loader,
        ).load()

    注意：
    - ``loader`` 必须提供（显式传 loader=None 保留旧的 skip 行为）。
    - 若平台后端不可用，记录 warning 并返回空字典。
    - 同名工具只生成一次；caller 传入的 ``tools`` 参数可在 ``create_agent`` 层覆盖。
    """

    def __init__(
        self,
        mounted_objects: list[str] | None = None,
        loader: Any = _LOADER_NOT_PROVIDED,
        skip_action_families: frozenset[str] = frozenset(),
        agent_friendly: bool = True,
        resource_path: str | Path | None = None,
        scene_ids: list[str] | None = None,
        base_id: str | None = None,
    ) -> None:
        self._scene_ids: list[str] | None = None
        self._base_id: str | None = None
        if scene_ids is not None:
            # scene_ids 模式：延迟 loader 构建，由 load() 中 _resolve_scene_loader 解析
            self._scene_ids = list(scene_ids)
            self._base_id = base_id
            self._loader: Any = loader if loader is not _LOADER_NOT_PROVIDED else None
        elif loader is not _LOADER_NOT_PROVIDED:
            # 显式传入 loader（可为 None，保持旧的 skip-on-None 行为）
            self._loader = loader
        else:
            raise ValueError("必须提供 loader")

        self._mounted_objects: list[str] = list(mounted_objects or [])
        self._skip_action_families = skip_action_families
        self._agent_friendly = agent_friendly
        self._resource_path: Path | None = Path(str(resource_path)) if resource_path else None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """
        加载所有挂载对象的 LangChain 工具。

        Returns:
            dict[str, StructuredTool]: key 为工具名，value 为 StructuredTool 实例。
        """
        if self._scene_ids:
            resolved_loader, resolved_objects = self._resolve_scene_loader()
            self._loader = resolved_loader
            self._mounted_objects = resolved_objects

        if not self._mounted_objects:
            return {}

        if self._loader is None:
            logger.debug(
                "OntologyToolLoader: loader 未提供，跳过本体工具生成 (mounted_objects=%s)",
                self._mounted_objects,
            )
            return {}

        tools: dict[str, Any] = {}

        for obj_code in self._mounted_objects:
            if self._is_view(obj_code):
                # VIEW 类型：直接读取 view.actions，对齐 ToolRegistry._append_view_tools
                view_tools = self._build_view_tools(obj_code)
                tools.update(view_tools)
            elif self._is_database_object(obj_code):
                # DB OBJECT：优先通过平台 generate_action_tools 生成所有动作工具
                # 前提：_build_shared_loader 已调用 inject_virtual_actions
                action_tools = self._build_action_tools(self._loader, obj_code)
                tools.update(action_tools)

                # 降级兜底：若未产出 query 族工具且未要求跳过，尝试 generate_dynamic_query_tools
                # 场景：inject_virtual_actions 未调用（旧环境或直接调用方跳过了注入）
                _query_prefix = get_settings().virtual_action_query_prefix
                if "query" not in self._skip_action_families and not any(
                    k.startswith(f"{_query_prefix}{obj_code}") for k in action_tools
                ):
                    query_tool = self._build_query_tool(self._loader, obj_code)
                    if query_tool is not None:
                        tools[query_tool.name] = query_tool
            else:
                # 非 DB OBJECT：直接根据对象下 action schema 生成工具
                object_tools = self._build_object_schema_tools(obj_code)
                tools.update(object_tools)

        logger.info(
            "OntologyToolLoader: 已生成 %d 个本体工具: %s",
            len(tools),
            sorted(tools.keys()),
        )
        return tools

    # ------------------------------------------------------------------
    # Scene 解析
    # ------------------------------------------------------------------

    def _resolve_scene_loader(self) -> tuple[Any, list[str]]:
        """根据 scene_ids 解析出 loader 和挂载对象列表。

        接口层和 AgentConfig 都使用 scene_id 通信，无需 scene_code→scene_id 转换。
        直接调用 platform.load_ontology_from_scenes 构建 loader，
        并提取 loader 中的 _classes / _views 作为 mounted_objects。
        """
        from datacloud_platform import get_platform  # noqa: PLC0415

        platform = get_platform()
        scene_ids = list(self._scene_ids or [])
        loader = platform.load_ontology_from_scenes(self._base_id, scene_ids)
        mounted_objects: list[str] = []
        if hasattr(loader, "_classes"):
            mounted_objects.extend(list(loader._classes.keys()))
        if hasattr(loader, "_views"):
            mounted_objects.extend(list(loader._views.keys()))
        return loader, mounted_objects

    # ------------------------------------------------------------------
    # Schema 个性化：_apply_agent_schema_patches
    # ------------------------------------------------------------------

    # query_* 工具不应暴露给 LLM 的 compute-only 字段
    _QUERY_ONLY_STRIP_FIELDS: frozenset[str] = frozenset({"dimensions", "metrics", "having"})

    def _apply_agent_schema_patches(
        self, scope_code: str, input_schema: dict[str, Any], *, action_type: str = ""
    ) -> dict[str, Any]:
        """agent_friendly=True 时对 query/compute 工具 schema 做全量修正。

        修正点：
          1. (query only) dimensions/metrics/having → 从 properties/required 中移除，
             避免 LLM 把 compute-only 字段填入 query 工具调用
          2. filters → 替换为 relaxed 版本（catch-all 兜底 + field 支持中文名 + 原词透传指令）
          3. select → description 替换为 AGENT_SELECT_DESCRIPTION
          4. order_by.field → description 替换为 AGENT_ORDER_BY_FIELD_DESCRIPTION
          5. complex_conditions → description 替换为 AGENT_COMPLEX_CONDITIONS_DESCRIPTION
        loader 查找失败时原样返回，降级为原始行为。
        """
        from datacloud_analysis.tools._agent_schema_patches import (  # noqa: PLC0415
            AGENT_COMPLEX_CONDITIONS_DESCRIPTION,
            AGENT_ORDER_BY_FIELD_DESCRIPTION,
            AGENT_SELECT_DESCRIPTION,
        )

        # 获取字段列表（OBJECT 路径优先，失败后尝试 VIEW 路径）
        fields: list[Any] = []
        try:
            obj = self._loader.get_ontology_class(scope_code)
            fields = list(obj.fields)
        except Exception:  # noqa: BLE001
            try:
                view = self._loader.get_view(scope_code)
                fields = list(getattr(view, "fields", []))
            except Exception:  # noqa: BLE001
                return input_schema  # 降级：loader 查找失败，原样返回

        props = dict(input_schema.get("properties") or {})

        # 1. (query only) 移除 compute-only 字段，LLM 不可见
        if action_type == "query":
            for _f in self._QUERY_ONLY_STRIP_FIELDS:
                props.pop(_f, None)
            required = [
                r
                for r in (input_schema.get("required") or [])
                if r not in self._QUERY_ONLY_STRIP_FIELDS
            ]
            input_schema = {**input_schema, "required": required}

        # 2. filters：替换为 relaxed 版本（含 catch-all + 原词透传描述）
        props["filters"] = get_platform().build_filters_schema(_base_id, fields)

        # 2. select：覆写 description，保留 enum 供 LLM 参考
        if "select" in props:
            select = dict(props["select"])
            select["description"] = AGENT_SELECT_DESCRIPTION
            props["select"] = select

        # 3. order_by.field：覆写 description，保留 enum 供 LLM 参考
        if "order_by" in props:
            order_by = dict(props["order_by"])
            items = dict(order_by.get("items") or {})
            item_props = dict(items.get("properties") or {})
            if "field" in item_props:
                field_prop = dict(item_props["field"])
                field_prop["description"] = AGENT_ORDER_BY_FIELD_DESCRIPTION
                item_props["field"] = field_prop
            items["properties"] = item_props
            order_by["items"] = items
            props["order_by"] = order_by

        # 4. complex_conditions：覆盖 description；若缺失则补一个可选数组字段
        complex_conditions = dict(props.get("complex_conditions") or {})
        if not complex_conditions:
            complex_conditions = {"type": "array", "items": {"type": "string"}, "default": []}
        complex_conditions["description"] = AGENT_COMPLEX_CONDITIONS_DESCRIPTION
        props["complex_conditions"] = complex_conditions

        return {**input_schema, "properties": props}

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _is_view(self, code: str) -> bool:
        """检查 code 是否为 VIEW 类型（在 loader._scenes 中）。"""
        scenes = getattr(self._loader, "_scenes", {})
        return code in scenes

    def _is_database_object(self, code: str) -> bool:
        """检查对象是否为 DB 类型。"""
        try:
            cls = self._loader.get_ontology_class(code)
        except Exception:  # noqa: BLE001
            return False
        return getattr(cls, "source_type", "") == "DB"

    @staticmethod
    def _get_action_family(action: Any) -> str:
        """优先返回 action_family，缺失时回退到 action_type。"""
        action_family = getattr(action, "action_family", "")
        if action_family:
            return action_family
        return getattr(action, "action_type", "")

    def _build_view_tools(self, view_code: str) -> dict[str, Any]:
        """为 VIEW 类型生成工具，对齐 ToolRegistry._append_view_tools 逻辑。"""
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            view = self._loader.get_view(view_code)
            for action in view.actions:
                # 跳过 skip_action_families 中的族（db_query 模式跳过 query/compute）
                # 用 action_family 而非 action_type：注入器将所有虚拟动作的 action_type 硬编码为
                # "query"，action_family 才是区分 query/compute 的正确字段。
                _view_action_family = self._get_action_family(action)
                if _view_action_family in self._skip_action_families:
                    continue
                exposure = getattr(action, "exposure_policy", "direct")
                if exposure == "hidden":
                    continue
                if not action.input_schema:
                    continue

                view_schema: dict[str, Any] = dict(action.input_schema)
                if self._agent_friendly and _view_action_family in {"query", "compute"}:
                    view_schema = self._apply_agent_schema_patches(
                        view_code, view_schema, action_type=_view_action_family
                    )

                result[action.action_code] = StructuredTool(
                    name=action.action_code,
                    description=action.description or action.action_name,
                    metadata={"title": action.action_name or action.action_code},
                    args_schema=view_schema,
                    coroutine=_make_view_action_coroutine(
                        view_code, action.action_code, self._loader
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OntologyToolLoader: 构建 VIEW %s 工具失败: %s", view_code, exc)
        return result

    def _build_object_schema_tools(self, obj_code: str) -> dict[str, Any]:
        """为非 DB OBJECT 直接根据对象动作 schema 生成工具。"""
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            obj = self._loader.get_object(obj_code)
            cls = self._loader.get_ontology_class(obj_code)
            for action in cls.actions:
                action_family = self._get_action_family(action)
                if action_family in self._skip_action_families:
                    continue

                exposure = getattr(action, "exposure_policy", "direct")
                if exposure == "hidden":
                    continue

                schema = obj.get_action_schema(action.action_code)
                name = str(schema.get("name", action.action_code))
                input_schema_raw = schema.get("inputSchema", {})
                input_schema = (
                    dict(input_schema_raw)
                    if isinstance(input_schema_raw, dict)
                    else {"type": "object", "properties": {}}
                )
                if self._agent_friendly and action_family in {"query", "compute"}:
                    input_schema = self._apply_agent_schema_patches(obj_code, input_schema)

                result[name] = StructuredTool(
                    name=name,
                    description=str(
                        schema.get("description") or action.description or action.action_name
                    ),
                    metadata={"title": str(schema.get("title") or action.action_name or name)},
                    args_schema=input_schema,
                    coroutine=_make_object_action_coroutine(
                        obj_code, action.action_code, self._loader
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OntologyToolLoader: 构建 OBJECT %s 工具失败: %s", obj_code, exc)
        return result

    def _build_action_tools(self, loader: Any, obj_code: str) -> dict[str, Any]:
        """为 DB OBJECT 通过平台生成动作工具（含 query / compute / OWL 自定义）。

        执行路径对齐 MCP call_tool 对象分支。
        需要 inject_virtual_actions 已在 loader 上调用，否则 cls.actions 为空，返回 {}。
        """
        result: dict[str, Any] = {}
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            for tool_def in get_platform().generate_action_tools(_base_id, loader, obj_code):
                name: str = tool_def.get("name", "")
                if not name:
                    continue

                meta = tool_def.get("_meta", {})
                action_family: str = meta.get("action_type", "")
                is_virtual: bool = meta.get("is_virtual", False)

                # 跳过需要排除的族（db_query 模式下跳过 query / compute 虚拟注入动作）
                if action_family in self._skip_action_families:
                    continue

                # 优先使用 _meta["action_code"]（唯一码，由 action_tool_generator 写入）
                # fallback 到工具名 name：ActionToolGenerator 保证 name == action.action_code
                action_code: str = meta.get("action_code") or name

                input_schema: dict[str, Any] = tool_def.get("inputSchema", {})

                if is_virtual and self._agent_friendly and action_family in {"query", "compute"}:
                    input_schema = self._apply_agent_schema_patches(
                        obj_code, input_schema, action_type=action_family
                    )
                try:
                    _raw_title = str(tool_def.get("title") or name)
                    if is_virtual and action_family in {"query", "compute"}:
                        _display_title = f"[内置]{_raw_title}"
                    else:
                        _display_title = _raw_title
                    result[name] = StructuredTool(
                        name=name,
                        description=tool_def.get("description", name),
                        metadata={"title": _display_title},
                        args_schema=input_schema,
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

    def _build_query_tool(self, loader: Any, obj_code: str) -> Any | None:
        """降级兜底：为对象通过平台生成 query_{code} 工具（inject_virtual_actions 未调用时使用）。

        正常路径（inject_virtual_actions 已调用）不走此处，通过 _build_action_tools 覆盖。
        """
        try:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            tool_defs = get_platform().generate_dynamic_query_tools(_base_id, loader, obj_code)
            if not tool_defs:
                logger.debug(
                    "OntologyToolLoader: %s 不是 DB/KB 类型，跳过 query 工具降级生成",
                    obj_code,
                )
                return None

            tool_def = tool_defs[0]

            logger.debug(
                "OntologyToolLoader: FALLBACK — 使用 generate_dynamic_query_tools 为 %s 生成 query 工具"
                "（请确认 inject_virtual_actions 已在 _build_shared_loader 中调用）",
                obj_code,
            )
            return StructuredTool(
                name=tool_def["name"],
                description=tool_def.get("description", tool_def["name"]),
                metadata={"title": str(tool_def.get("title") or tool_def["name"])},
                args_schema=tool_def.get("inputSchema", {}),
                coroutine=_make_tool_coroutine(None, loader),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OntologyToolLoader: 构建 query_%s 工具失败: %s", obj_code, exc)
            return None

    # ------------------------------------------------------------------
    # NL 查询工具工厂（阶段二 V-2 迁移）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_enum_context(entity: Any, resource_path: Any = None) -> str:
        """从 view/object 的字段定义里提取 enum 字段的字典映射，构建 contextKnowledge 字符串。

        扫描 term_type='enum' 的字段，从 term_values 目录读取对应的 OWL 文件，
        生成"字段名: 值1=含义1, 值2=含义2, ..." 格式的说明，注入给 LLM 作为背景知识。
        """
        try:
            fields = list(getattr(entity, "fields", []) or [])
            if not fields:
                return ""

            # 收集所有 enum 字段的 term_set（格式为 "{dict_type}.code"）
            enum_fields: dict[str, list[str]] = {}  # dict_type -> [field_desc, ...]
            for f in fields:
                if getattr(f, "term_type", None) == "enum":
                    term_set = str(getattr(f, "term_set", "") or "")
                    if term_set.endswith(".code"):
                        dict_type = term_set[:-5]  # 去掉 ".code"
                        prop_code = str(getattr(f, "property_code", "") or "")
                        prop_name = str(getattr(f, "property_name", "") or prop_code)
                        if dict_type not in enum_fields:
                            enum_fields[dict_type] = []
                        enum_fields[dict_type].append(f"{prop_code}（{prop_name}）")

            if not enum_fields:
                return ""

            if resource_path is None:
                return ""

            import xml.etree.ElementTree as ET  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            rp = Path(str(resource_path))
            # term_values 目录在 resource_path 的父目录下，或同级
            for candidate in [rp.parent / "term_values", rp / "term_values"]:
                if candidate.exists():
                    term_values_dir = candidate
                    break
            else:
                return ""

            lines: list[str] = ["## 字段字典编码说明（过滤条件必须使用编码值，不能使用显示名称）"]
            for dict_type, field_names in sorted(enum_fields.items()):
                owl_file = term_values_dir / dict_type / f"{dict_type}_terms.owl"
                if not owl_file.exists():
                    continue
                try:
                    tree = ET.parse(str(owl_file))
                    root = tree.getroot()
                    ns = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"}
                    ent_ns = "http://example.org/entity/ontology#"
                    mappings: list[str] = []
                    for desc in root.findall(".//rdf:Description", ns):
                        code_el = desc.find(f"{{{ent_ns}}}term_code")
                        name_el = desc.find(f"{{{ent_ns}}}term_name")
                        type_el = desc.find(f"{{{ent_ns}}}term_type_code")
                        if (
                            code_el is not None
                            and name_el is not None
                            and type_el is not None
                            and type_el.text == dict_type
                            and code_el.text != dict_type
                        ):
                            mappings.append(f"{code_el.text}={name_el.text}")
                    if mappings:
                        field_list = "、".join(field_names)
                        lines.append(f"- 字段 {field_list}：{', '.join(sorted(mappings))}")
                except Exception:  # noqa: BLE001
                    pass

            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception:  # noqa: BLE001
            return ""

    def build_all_nl_query_tools(self) -> dict[str, Any]:
        """为所有已挂载的 view/object 批量生成 data_query_* 工具。

        返回 dict[tool_name, StructuredTool]，供 build_analysis_graph(redirect_tools=...) 使用。
        """
        if not self._mounted_objects or self._loader is None:
            return {}

        result: dict[str, Any] = {}
        for code in self._mounted_objects:
            try:
                if self._is_view(code):
                    entity = self._loader.get_view(code)
                    biz_type = "VIEW"
                else:
                    entity = self._loader.get_object(code)
                    biz_type = "OBJECT"
                name = getattr(entity, "name", None) or getattr(entity, "view_name", None) or code
                desc = getattr(entity, "description", None) or ""
                enum_context = self._build_enum_context(entity, self._resource_path)
                tool = self.build_nl_query_tool(
                    resource_code=code,
                    resource_biz_type=biz_type,
                    resource_name=str(name),
                    resource_desc=str(desc),
                    default_context_knowledge=enum_context,
                )
                result[tool.name] = tool
            except Exception as exc:  # noqa: BLE001
                logger.warning("OntologyToolLoader: 构建 data_query_%s 工具失败: %s", code, exc)
        logger.info(
            "OntologyToolLoader: 已生成 %d 个 NL 查询工具: %s",
            len(result),
            sorted(result.keys()),
        )
        return result

    def build_nl_query_tool(
        self,
        resource_code: str,
        resource_biz_type: str,
        resource_name: str,
        resource_desc: str,
        *,
        inject_context_knowledge: bool = True,
        default_context_knowledge: str = "",
    ) -> Any:
        """生成自然语言查询 StructuredTool，名称为 data_query_{resource_code}。

        Args:
            resource_code: 资源编码（OBJECT/VIEW code）。
            resource_biz_type: 业务类型，"OBJECT" 或 "VIEW"。
            resource_name: 资源名称（工具描述中使用）。
            resource_desc: 资源描述（工具描述补充，取首行）。
            inject_context_knowledge: True 时在 schema 中注入 contextKnowledge 字段。
            default_context_knowledge: 系统预置的上下文知识（如字典编码说明），
                当调用方未传 contextKnowledge 时自动使用。

        Returns:
            StructuredTool，名称为 data_query_{resource_code}。
        """
        from langchain_core.tools import StructuredTool  # noqa: PLC0415
        from pydantic import BaseModel, Field, create_model  # noqa: PLC0415

        loader = self._loader
        tool_name = f"data_query_{resource_code}"

        schema_name = f"_NLQuery{resource_code}Schema"
        if schema_name in _DYNAMIC_SCHEMA_REGISTRY:
            schema_cls = _DYNAMIC_SCHEMA_REGISTRY[schema_name]
        else:
            from datacloud_analysis.tools._agent_schema_patches import (  # noqa: PLC0415
                AGENT_QUERY_DESCRIPTION,
            )

            model_fields: dict[str, Any] = {
                "query": (str, Field(description=AGENT_QUERY_DESCRIPTION)),
            }
            if inject_context_knowledge:
                model_fields["contextKnowledge"] = (
                    str,
                    Field(
                        default="",
                        description="Context knowledge injected by the system — do not fill.",
                    ),
                )
            schema_cls = create_model(schema_name, __base__=BaseModel, **model_fields)
            schema_cls.__module__ = __name__
            setattr(sys.modules[__name__], schema_name, schema_cls)
            _DYNAMIC_SCHEMA_REGISTRY[schema_name] = schema_cls

        async def _execute(query: str, contextKnowledge: str = "") -> Any:  # noqa: N803
            if resource_biz_type == "VIEW":
                entity = loader.get_view(resource_code)
            else:
                entity = loader.get_object(resource_code)
            # 合并系统预置上下文和调用方传入的上下文
            merged_context = (
                "\n\n".join(p for p in [default_context_knowledge, contextKnowledge] if p) or None
            )
            return await entity.query(question=query, knowledge_context=merged_context)

        desc = f"数据查询工具: {resource_name or resource_code}"
        if resource_desc:
            first_line = resource_desc.split("\n")[0]
            if first_line:
                desc = f"{desc}。{first_line}"

        return StructuredTool.from_function(
            func=None,
            coroutine=_execute,
            name=tool_name,
            description=desc,
            args_schema=schema_cls,
        )
