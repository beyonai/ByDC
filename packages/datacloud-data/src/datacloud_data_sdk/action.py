"""
动作(Action)实体模块

本模块定义了 Action 类，用于封装本体动作(OntologyAction)，提供 schema 生成与执行能力。
Action 是数据服务中执行操作的核心抽象，支持多种执行方式：脚本执行、API调用、虚拟查询等。

核心功能：
- 动作 schema 生成：生成符合 JSON Schema 规范的输入输出定义
- 参数映射：支持参数名/别名的自动映射
- 多执行模式：script(脚本) -> function_refs(API) -> 虚拟查询
- 术语解析：自动解析业务术语到实际值

执行优先级：
1. is_virtual=True: 执行虚拟查询（动态构建 SQL）
2. script 存在: 执行脚本代码
3. function_refs 存在: 调用外部 API
4. 否则抛出 ActionNotConfiguredError

使用示例：
    action = Action(ontology_action, loader=ontology_loader)
    schema = action.get_schema()  # 获取 JSON Schema
    result = await action.execute({"param1": "value1"})  # 执行动作
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any
from urllib.parse import quote

from datacloud_data_sdk.ontology.models import OntologyAction, OntologyActionParam, OntologyField

logger = logging.getLogger(__name__)


def _safe_copy(value: Any) -> Any:
    """尽量深拷贝调试信息，失败时回退原值。"""
    try:
        return deepcopy(value)
    except Exception:
        return value


def _append_execution_step(
    steps: list[dict[str, Any]] | None,
    *,
    step: str,
    title: str,
    status: str = "completed",
    data: dict[str, Any] | None = None,
) -> None:
    """向动作执行明细中追加一步。"""
    if steps is None:
        return

    payload: dict[str, Any] = {
        "step": step,
        "title": title,
        "status": status,
    }
    if data is not None:
        payload["data"] = _safe_copy(data)
    steps.append(payload)


async def _emit_execution_step(
    *,
    step: str,
    title: str,
    status: str = "completed",
    data: dict[str, Any] | None = None,
) -> None:
    """通过 gateway_context 将动作步骤实时推送出去。（已禁用）"""


def _translate_view_params(view: Any, params: dict[str, Any]) -> dict[str, Any]:
    """将 query/compute 视图动作参数中的字段中文名翻译为 property_code。

    视图字段 property_name（中文名）→ property_code，供 ViewLookupExecutor /
    ViewAnalyzeExecutor 消费（它们使用 property_code 作字段标识）。
    """
    from typing import Any as _Any

    name_to_code: dict[str, str] = {}
    for vf in getattr(view, "fields", []):
        pname = getattr(vf, "property_name", "")
        pcode = getattr(vf, "property_code", "")
        if pname and pcode:
            name_to_code[pname] = pcode

    if not name_to_code:
        return params

    translated: dict[str, _Any] = dict(params)

    if "select" in params:
        translated["select"] = [name_to_code.get(n, n) for n in (params["select"] or [])]

    if "filters" in params:
        new_filters = []
        for item in params["filters"] or []:
            new_item = dict(item)
            fname = item.get("field", "")
            new_item["field"] = name_to_code.get(fname, fname)
            new_filters.append(new_item)
        translated["filters"] = new_filters

    if "order_by" in params:
        new_order = []
        for ob in params["order_by"] or []:
            new_ob = dict(ob)
            fname = ob.get("field", "")
            new_ob["field"] = name_to_code.get(fname, fname)
            new_order.append(new_ob)
        translated["order_by"] = new_order

    if "dimensions" in params:
        new_dims = []
        for dim in params["dimensions"] or []:
            if isinstance(dim, str):  # 兼容 LLM 传字符串的情况，自动包装为 {"field": dim}
                dim = {"field": dim}
            new_dim = dict(dim)
            fname = dim.get("field", "")
            new_dim["field"] = name_to_code.get(fname, fname)
            new_dims.append(new_dim)
        translated["dimensions"] = new_dims

    if "metrics" in params:
        new_metrics = []
        for mtr in params["metrics"] or []:
            new_mtr = dict(mtr)
            if "field" in mtr:
                fname = mtr.get("field", "")
                new_mtr["field"] = name_to_code.get(fname, fname)
            new_metrics.append(new_mtr)
        translated["metrics"] = new_metrics

    return translated


def _default_query_output_schema() -> dict[str, object]:
    """
    生成虚拟动作的默认输出 schema

    虚拟动作通常返回记录列表和总数，此函数提供标准化的输出格式定义。

    Returns:
        dict: 包含 records 数组和 total 整数的 JSON Schema
    """
    return {
        "type": "object",
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}, "description": "记录行"},
            "total": {"type": "integer", "description": "总条数"},
        },
    }


PARAM_TYPE_MAP: dict[str, str] = {
    "STRING": "string",
    "NUMBER": "number",
    "DECIMAL": "number",
    "DOUBLE": "number",
    "FLOAT": "number",
    "INTEGER": "integer",
    "INT": "integer",
    "BIGINT": "integer",
    "LONG": "integer",
    "BOOLEAN": "boolean",
    "DATE": "string",
    "DATETIME": "string",
    "TIMESTAMP": "string",
    "ARRAY": "array",
    "LIST": "array",
    "OBJECT": "object",
}
"""本体参数类型到 JSON Schema 类型的映射表

将本体定义中的参数类型（如 STRING, INTEGER）映射到 JSON Schema 标准类型。
"""

_MAPPING_LOCATION_ALIASES: dict[str, str] = {
    "requestBody": "body",
    "body": "body",
    "parameters": "body",
    "query": "query",
    "queryParams": "query",
    "path": "path",
    "pathParams": "path",
    "headers": "headers",
    "header": "headers",
}
_INPUT_LOCATION_ROOT_KEYS: dict[str, tuple[str, ...]] = {
    "body": ("requestBody", "body", "parameters"),
    "query": ("query", "queryParams"),
    "path": ("path", "pathParams"),
    "headers": ("headers", "header"),
}
_LOCATION_SCHEMA_KEYS: dict[str, str] = {
    "body": "requestBody",
    "query": "query",
    "path": "path",
    "headers": "headers",
}
_WRAPPER_INPUT_KEYS = frozenset(
    {
        "requestBody",
        "body",
        "parameters",
        "query",
        "queryParams",
        "path",
        "pathParams",
        "headers",
        "header",
    }
)
_MISSING = object()
_OPERATION_CONFIRM_PARAM = "userConfirmed"
_OPERATION_CONFIRM_PARAM_ALIASES = frozenset({_OPERATION_CONFIRM_PARAM, "user_confirmed"})
_OPERATION_CONFIRMATION_CACHE: dict[str, dict[str, Any]] = {}


def _normalize_mapping_location(location: str) -> str:
    """归一化 mapping_path 位置前缀。"""
    return _MAPPING_LOCATION_ALIASES.get(location, location)


def _parse_mapping_path(
    mapping_path: str,
    *,
    default_location: str,
) -> tuple[str, list[str]]:
    """解析 mapping_path，返回归一化后的 location 与剩余路径。"""
    normalized_default = _normalize_mapping_location(default_location)
    if not mapping_path.startswith("$."):
        return normalized_default, []

    parts = [part for part in mapping_path[2:].split(".") if part]
    if not parts:
        return normalized_default, []

    first_part = parts[0]
    if first_part in _MAPPING_LOCATION_ALIASES:
        return _normalize_mapping_location(first_part), parts[1:]
    return normalized_default, parts


def _schema_location_key(location: str) -> str:
    """将运行时位置映射为 input schema 顶层 key。"""
    normalized = _normalize_mapping_location(location)
    return _LOCATION_SCHEMA_KEYS.get(normalized, normalized)


def _append_required(schema: dict[str, Any], field_name: str) -> None:
    """为 schema 节点追加 required 字段。"""
    required = schema.setdefault("required", [])
    if isinstance(required, list) and field_name not in required:
        required.append(field_name)


def _ensure_object_schema(schema: dict[str, Any]) -> None:
    """确保 schema 节点为 object。"""
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})


def _ensure_array_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """确保 schema 节点为数组，并返回 items 节点。"""
    schema.setdefault("type", "array")
    items = schema.setdefault("items", {"type": "object", "properties": {}})
    if isinstance(items, dict):
        items.setdefault("type", "object")
        items.setdefault("properties", {})
        return items
    schema["items"] = {"type": "object", "properties": {}}
    return schema["items"]


def _assign_schema_path(
    root: dict[str, Any],
    path_parts: list[str],
    leaf_schema: dict[str, Any],
    *,
    required: bool,
) -> None:
    """将叶子 schema 按 path_parts 合并到根节点。"""
    if not path_parts:
        _ensure_object_schema(root)
        properties = root.setdefault("properties", {})
        if isinstance(properties, dict):
            properties.update(leaf_schema)
        return

    current = root
    index = 0
    if path_parts and path_parts[0] == "[]":
        if len(path_parts) == 1:
            root.clear()
            root.update({"type": "array", "items": leaf_schema})
            return
        current = _ensure_array_schema(root)
        index = 1

    for raw_part in path_parts[index:]:
        is_last = raw_part == path_parts[-1]
        is_array = raw_part.endswith("[]")
        part = raw_part[:-2] if is_array else raw_part
        _ensure_object_schema(current)
        properties = current.setdefault("properties", {})
        if not isinstance(properties, dict):
            current["properties"] = {}
            properties = current["properties"]

        if is_last:
            if is_array:
                properties[part] = {"type": "array", "items": leaf_schema}
            else:
                properties[part] = leaf_schema
            if required:
                _append_required(current, part)
            return

        if required:
            _append_required(current, part)
        if is_array:
            node = properties.setdefault(
                part, {"type": "array", "items": {"type": "object", "properties": {}}}
            )
            if not isinstance(node, dict):
                node = {"type": "array", "items": {"type": "object", "properties": {}}}
                properties[part] = node
            current = _ensure_array_schema(node)
        else:
            node = properties.setdefault(part, {"type": "object", "properties": {}})
            if not isinstance(node, dict):
                node = {"type": "object", "properties": {}}
                properties[part] = node
            _ensure_object_schema(node)
            current = node


def _extract_structured_value(value: Any, path_parts: list[str]) -> Any:
    """从嵌套输入结构中提取 mapping_path 对应的值。"""
    if not path_parts:
        return value

    head = path_parts[0]
    tail = path_parts[1:]
    if head == "[]":
        if not isinstance(value, list):
            return _MISSING
        if not tail:
            return value
        extracted_items: list[Any] = []
        for item in value:
            extracted = _extract_structured_value(item, tail)
            extracted_items.append(None if extracted is _MISSING else extracted)
        return extracted_items

    if head.endswith("[]"):
        key = head[:-2]
        if not isinstance(value, dict):
            return _MISSING
        child = value.get(key, _MISSING)
        if child is _MISSING or not isinstance(child, list):
            return _MISSING
        if not tail:
            return child
        extracted_items = []
        for item in child:
            extracted = _extract_structured_value(item, tail)
            extracted_items.append(None if extracted is _MISSING else extracted)
        return extracted_items

    if not isinstance(value, dict):
        return _MISSING
    child = value.get(head, _MISSING)
    if child is _MISSING:
        return _MISSING
    return _extract_structured_value(child, tail)


def _coerce_sequence(value: Any) -> list[Any]:
    """将值标准化为 list，用于数组路径赋值。"""
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _coerce_confirm_flag(value: Any) -> bool:
    """将确认参数归一化为布尔值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _is_missing_required_value(value: Any) -> bool:
    """判断必填参数是否缺失。"""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple)):
        return len(value) == 0 or any(_is_missing_required_value(item) for item in value)
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _make_runtime_container(path_parts: list[str]) -> Any:
    """根据剩余路径推断运行时容器类型。"""
    if path_parts and path_parts[0] == "[]":
        return []
    return {}


def _assign_runtime_path(container: Any, path_parts: list[str], value: Any) -> Any:
    """按 path_parts 将值写入运行时请求结构。"""
    if not path_parts:
        return value

    head = path_parts[0]
    tail = path_parts[1:]
    if head == "[]":
        values = _coerce_sequence(value)
        if not tail:
            return values
        result = container if isinstance(container, list) else []
        while len(result) < len(values):
            result.append(_make_runtime_container(tail))
        for index, item_value in enumerate(values):
            result[index] = _assign_runtime_path(result[index], tail, item_value)
        return result

    if head.endswith("[]"):
        key = head[:-2]
        current = container if isinstance(container, dict) else {}
        values = _coerce_sequence(value)
        if not tail:
            current[key] = values
            return current
        items = current.get(key)
        if not isinstance(items, list):
            items = []
        while len(items) < len(values):
            items.append(_make_runtime_container(tail))
        for index, item_value in enumerate(values):
            items[index] = _assign_runtime_path(items[index], tail, item_value)
        current[key] = items
        return current

    current = container if isinstance(container, dict) else {}
    if not tail:
        current[head] = value
        return current
    next_container = current.get(head)
    if not isinstance(next_container, (dict, list)):
        next_container = _make_runtime_container(tail)
    current[head] = _assign_runtime_path(next_container, tail, value)
    return current


class Action:
    """
    动作实体类，提供 schema 生成与执行能力

    Action 是数据服务中执行操作的核心抽象。每个动作对应一个本体中定义的操作，
    可以是数据库查询、API调用或脚本执行。

    执行优先级：
        1. is_virtual=True: 执行虚拟查询（动态构建 SQL）
        2. script 存在: 执行脚本代码
        3. function_refs 存在: 调用外部 API
        4. 否则抛出 ActionNotConfiguredError

    Attributes:
        _action: 本体动作定义对象
        _loader: 本体加载器，用于获取相关配置和资源

    Example:
        action = Action(ontology_action, loader=ontology_loader)
        schema = action.get_schema()
        result = await action.execute({"status": "active"})
    """

    def __init__(self, ontology_action: OntologyAction, loader: Any = None) -> None:
        """
        初始化动作实体

        Args:
            ontology_action: 本体动作定义
            loader: 本体加载器实例，用于获取数据源配置等
        """
        self._action = ontology_action
        self._loader = loader

    @property
    def action_code(self) -> str:
        """动作代码，唯一标识此动作"""
        return self._action.action_code

    @property
    def has_script(self) -> bool:
        """是否配置了执行脚本"""
        return bool(self._action.script)

    def get_schema(self) -> dict[str, object]:
        """
        生成动作的 JSON Schema

        生成包含 name, title, description, inputSchema, outputSchema 的完整 schema。
        结果会被缓存，避免重复计算。

        Returns:
            dict: 包含动作元数据和输入输出 schema 的字典
        """
        if self._action._schema_cache is not None:
            return self._action._schema_cache
        if self._action.input_schema is not None:
            inp = self._action.input_schema
            out = self._action.output_schema or _default_query_output_schema()
        else:
            in_params = [p for p in self._action.params if p.direction in ("IN", "INOUT")]
            out_params = [p for p in self._action.params if p.direction in ("OUT", "INOUT")]
            inp = self._build_input_schema(in_params)
            out = self._build_schema(out_params)
        result = {
            "name": self._action.action_code,
            "title": self._action.action_name or self._action.action_code,
            "description": self._action.description or self._action.action_name or "",
            "inputSchema": inp,
            "outputSchema": out,
        }
        self._action._schema_cache = result
        return result

    def _build_input_schema(self, params: list[OntologyActionParam]) -> dict[str, object]:
        """为非虚拟动作构造输入 schema，支持 requestBody/query/path 分层。"""
        schema: dict[str, Any] = {"type": "object", "properties": {}}
        is_confirmable_operation = self._is_confirmable_operation()
        if not params:
            if is_confirmable_operation:
                self._inject_operation_confirm_schema(schema)
            return schema

        has_structured_mapping = any(
            getattr(param, "mapping_path", "").startswith("$.") for param in params
        )
        if not has_structured_mapping and not is_confirmable_operation:
            return self._build_schema(params)

        wrapper_required: set[str] = set()
        properties = schema["properties"]
        for param in params:
            leaf_schema = self._build_param_schema(param)
            schema_required = False if is_confirmable_operation else param.required
            location, path_parts = _parse_mapping_path(
                getattr(param, "mapping_path", ""),
                default_location="body",
            )
            location_key = _schema_location_key(location)
            if not path_parts:
                properties[param.param_code] = leaf_schema
                if schema_required:
                    wrapper_required.add(param.param_code)
                continue

            node = properties.setdefault(location_key, {})
            if not isinstance(node, dict):
                node = {}
                properties[location_key] = node
            _assign_schema_path(
                node,
                path_parts,
                leaf_schema,
                required=schema_required,
            )
            if schema_required:
                wrapper_required.add(location_key)

        if wrapper_required:
            schema["required"] = sorted(wrapper_required)
        if is_confirmable_operation:
            self._inject_operation_confirm_schema(schema)
        return schema

    @staticmethod
    def _inject_operation_confirm_schema(schema: dict[str, Any]) -> None:
        """为操作类动作注入统一的用户确认参数。"""
        properties = schema.setdefault("properties", {})
        if isinstance(properties, dict):
            properties[_OPERATION_CONFIRM_PARAM] = {
                "type": "boolean",
                "description": "用户是否确认按当前参数执行操作。首次提交请传 false，确认执行时传 true。",
            }
        schema["required"] = [_OPERATION_CONFIRM_PARAM]

    def _build_schema(self, params: list[OntologyActionParam]) -> dict[str, object]:
        """
        从参数列表构建 JSON Schema

        Args:
            params: 动作参数列表

        Returns:
            dict: JSON Schema 对象
        """
        properties: dict[str, dict[str, object]] = {}
        required: list[str] = []
        for p in params:
            prop = self._build_param_schema(p)
            if p.default_value is not None:
                prop["default"] = p.default_value
            properties[p.param_code] = prop
            if p.required:
                required.append(p.param_code)
        schema: dict[str, object] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _build_param_schema(self, param: OntologyActionParam) -> dict[str, object]:
        """构造单个参数的 JSON Schema。"""
        raw_type = (param.param_type or "STRING").upper()
        schema_type = PARAM_TYPE_MAP.get(raw_type, "string")
        schema: dict[str, object] = {
            "type": schema_type,
            "description": param.param_name,
        }

        if raw_type in ("DATE",):
            schema["format"] = "date"
        elif raw_type in ("DATETIME", "TIMESTAMP"):
            schema["format"] = "date-time"
        elif raw_type in ("DECIMAL", "DOUBLE", "FLOAT"):
            schema["format"] = raw_type.lower()
        elif raw_type in ("ARRAY", "LIST"):
            schema["items"] = {"type": "string"}

        self._inject_term_schema(schema, param)
        return schema

    def _inject_term_schema(
        self,
        schema: dict[str, object],
        param: OntologyActionParam,
    ) -> None:
        """将可落到标准 Schema 的术语信息注入参数 schema。"""
        if param.term_type != "enum" or not param.term_set:
            return

        enum_schema = self._get_enum_target_schema(schema)
        if enum_schema is None:
            return

        term_loader = self._get_term_loader()
        if term_loader is None:
            return

        term_type_code = self._get_term_type_code(param.term_set)
        entries = self._get_term_entries(
            term_loader,
            term_set=param.term_set,
            dataset_id=param.dataset_id,
            term_type_code=term_type_code,
        )
        enum_codes = [entry["code"] for entry in entries if entry.get("code")]
        if not enum_codes:
            return

        enum_schema["enum"] = enum_codes

    @staticmethod
    def _get_enum_target_schema(schema: dict[str, object]) -> dict[str, object] | None:
        """获取应注入 enum 的 schema 节点。"""
        if schema.get("type") == "array":
            items = schema.get("items")
            return items if isinstance(items, dict) else None
        return schema

    def _get_term_loader(self) -> Any:
        """获取 loader 上配置的术语加载器。"""
        if self._loader is None:
            return None
        return getattr(self._loader._config, "term_loader", None)

    @staticmethod
    def _get_term_type_code(term_set: str) -> str | None:
        """从 term_set 推导 term_type_code。"""
        if "." not in term_set:
            return None
        return term_set.split(".", 1)[0]

    @staticmethod
    def _get_term_entries(
        term_loader: Any,
        *,
        term_set: str,
        dataset_id: int | None,
        term_type_code: str | None,
    ) -> list[dict[str, str]]:
        """获取术语条目列表，优先使用条目接口，失败时回退到 code/value。"""
        try:
            entries = term_loader.get_entries(
                term_set,
                dataset_id=dataset_id,
                term_type_code=term_type_code,
            )
        except Exception:
            entries = []

        normalized_entries: list[dict[str, str]] = []
        for entry in entries:
            code = entry.get("code")
            if not code:
                continue
            normalized_entries.append(
                {
                    "code": str(code),
                    "label": str(entry.get("label", code)),
                }
            )
        if normalized_entries:
            return normalized_entries

        try:
            codes = term_loader.get_codes(
                term_set,
                dataset_id=dataset_id,
                term_type_code=term_type_code,
            )
        except Exception:
            codes = []
        return [{"code": str(code), "label": str(code)} for code in codes if code]

    def _map_names(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        将参数名/别名映射为标准的参数代码

        支持使用 param_name 或 alias 作为参数名，自动转换为 param_code。

        Args:
            arguments: 原始参数字典，可能使用别名作为键

        Returns:
            dict: 键为 param_code 的参数字典
        """
        alias_map: dict[str, str] = {}
        for p in self._action.params:
            alias_map[p.param_code] = p.param_code
            alias_map[p.param_name] = p.param_code
        mapped: dict[str, Any] = {}
        for key, value in arguments.items():
            param_code = alias_map.get(key, key)
            mapped[param_code] = value
        return mapped

    def _default_request_location(self) -> str:
        """推断当前动作默认的请求位置。"""
        if self._action.function_refs and self._loader:
            config = self._loader.get_function_config(self._action.function_refs[0])
            if config:
                method, _ = self._get_request_target(config)
                if method.upper() in {"GET", "DELETE", "HEAD"}:
                    return "query"
        return "body"

    def _find_input_value(
        self,
        arguments: dict[str, Any],
        param: OntologyActionParam,
        *,
        default_location: str,
    ) -> Any:
        """从平铺或结构化参数中读取指定动作参数值。"""
        for candidate in (param.param_code, param.param_name):
            if candidate and candidate in arguments:
                return arguments[candidate]

        location, path_parts = _parse_mapping_path(
            param.mapping_path, default_location=default_location
        )
        for root_key in _INPUT_LOCATION_ROOT_KEYS.get(location, ()):
            root_value = arguments.get(root_key, _MISSING)
            if root_value is _MISSING:
                continue
            extracted = _extract_structured_value(root_value, path_parts)
            if extracted is not _MISSING:
                return extracted
        return _MISSING

    def _normalize_input_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """将结构化输入参数还原为 param_code -> value。"""
        normalized: dict[str, Any] = {}
        consumed_keys: set[str] = set()
        default_location = self._default_request_location()
        for param in self._action.params:
            if param.direction not in ("IN", "INOUT"):
                continue
            value = self._find_input_value(arguments, param, default_location=default_location)
            if value is _MISSING:
                continue
            normalized[param.param_code] = value
            consumed_keys.update({param.param_code, param.param_name})

        for key, value in arguments.items():
            if key in consumed_keys or key in _WRAPPER_INPUT_KEYS:
                continue
            normalized.setdefault(key, value)
        return normalized

    def _is_confirmable_operation(self) -> bool:
        """是否为需要二次确认的操作类动作。"""
        return not bool(getattr(self._action, "is_virtual", False)) and (
            getattr(self._action, "action_type", "") == "operation"
        )

    def _build_operation_confirmation_cache_key(self) -> str:
        """构造操作确认缓存 key。"""
        try:
            from datacloud_data_sdk.context import get_current_context

            ctx = get_current_context()
            return (
                f"{ctx.tenant_id}|{ctx.user_id}|{ctx.session_id}|{ctx.system_code}|"
                f"{self._action.belong_class}|{self._action.action_code}"
            )
        except Exception:
            return (
                f"loader:{id(self._loader)}|{self._action.belong_class}|{self._action.action_code}"
            )

    def _get_cached_operation_confirmation(self) -> dict[str, Any] | None:
        """获取当前动作的待确认缓存。"""
        return _safe_copy(
            _OPERATION_CONFIRMATION_CACHE.get(self._build_operation_confirmation_cache_key())
        )

    def _set_cached_operation_confirmation(self, params: dict[str, Any]) -> None:
        """写入当前动作的待确认缓存。"""
        _OPERATION_CONFIRMATION_CACHE[self._build_operation_confirmation_cache_key()] = _safe_copy(
            params
        )

    def _clear_cached_operation_confirmation(self) -> None:
        """清理当前动作的待确认缓存。"""
        _OPERATION_CONFIRMATION_CACHE.pop(self._build_operation_confirmation_cache_key(), None)

    @staticmethod
    def _build_operation_feedback_message(
        *,
        missing_required: list[dict[str, str]],
        term_errors: list[dict[str, Any]],
        confirmation_state: str,
    ) -> str:
        """构造操作确认/校验反馈文案。"""
        lines: list[str] = []
        if missing_required:
            params_text = "、".join(
                f"{item['param_name']}({item['param_code']})" for item in missing_required
            )
            lines.append(f"以下必填参数未填写：{params_text}。")
        if term_errors:
            lines.append("以下参数术语转换未通过：")
            lines.extend(
                f"- {item['param_name']}({item['param_code']}): {item['message']}"
                for item in term_errors
            )
        if confirmation_state == "pending_confirmation":
            lines.append("参数校验通过，请确认以下参数后再次提交，并将 userConfirmed 设为 true。")
        elif confirmation_state == "confirm_without_cache":
            lines.append("当前没有待确认缓存，已为你缓存本次参数，请核对后再次确认。")
        elif confirmation_state == "confirm_mismatch":
            lines.append("本次确认参数与上次待确认参数不一致，已更新缓存，请核对后再次确认。")
        return "\n".join(lines)

    async def _record_operation_step(
        self,
        execution_steps: list[dict[str, Any]] | None,
        *,
        step: str,
        title: str,
        status: str = "completed",
        data: dict[str, Any] | None = None,
    ) -> None:
        """记录操作类动作前置校验步骤。"""
        _append_execution_step(
            execution_steps,
            step=step,
            title=title,
            status=status,
            data=data,
        )
        await _emit_execution_step(
            step=step,
            title=title,
            status=status,
            data=data,
        )

    async def _resolve_operation_terms(
        self,
        params: dict[str, Any],
        *,
        term_loader: Any = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """对操作类动作执行逐参数术语转换，并汇总全部错误。"""
        resolved = dict(params)
        errors: list[dict[str, Any]] = []
        if term_loader is None:
            return resolved, errors

        from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError
        from datacloud_data_sdk.plan.term_resolver import TermResolver

        resolver = TermResolver(term_loader)
        for param in self._action.params:
            if param.direction not in ("IN", "INOUT") or not param.term_set:
                continue
            if param.param_code not in params or params[param.param_code] is None:
                continue
            try:
                resolved[param.param_code] = resolver._resolve_term_value(
                    term_set=param.term_set,
                    term_type=param.term_type,
                    term_field=param.term_field,
                    dataset_id=param.dataset_id,
                    raw_value=params[param.param_code],
                    param_name=param.param_name or param.param_code,
                )
            except (TermNotFoundError, TermAmbiguousError) as exc:
                errors.append(
                    {
                        "param_code": param.param_code,
                        "param_name": param.param_name or param.param_code,
                        "message": str(exc),
                        "error_type": exc.__class__.__name__,
                        "raw_value": _safe_copy(params[param.param_code]),
                    }
                )
            except ValueError as exc:
                errors.append(
                    {
                        "param_code": param.param_code,
                        "param_name": param.param_name or param.param_code,
                        "message": str(exc),
                        "error_type": "ValueError",
                        "raw_value": _safe_copy(params[param.param_code]),
                    }
                )
        return resolved, errors

    async def _build_operation_ask_user_response(
        self,
        *,
        message: str,
        original_params: dict[str, Any],
        normalized_params: dict[str, Any],
        resolved_params: dict[str, Any],
        missing_required: list[dict[str, str]],
        term_errors: list[dict[str, Any]],
        user_confirmed: bool,
        cache_status: str,
        execution_steps: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """构造操作类动作的 ask_user 返回。"""
        from datacloud_data_sdk.result_formatter import build_error_data

        payload = build_error_data(
            message,
            result_type="ask_user",
            extra={
                "submitted_params": _safe_copy(original_params),
                "normalized_params": _safe_copy(normalized_params),
                "resolved_params": _safe_copy(resolved_params),
                "missing_required_params": _safe_copy(missing_required),
                "term_errors": _safe_copy(term_errors),
                "confirmation": {
                    "user_confirmed": user_confirmed,
                    "cache_status": cache_status,
                },
            },
        )
        if execution_steps is not None:
            payload["execution_steps"] = execution_steps
        return payload

    async def _prepare_confirmable_operation(
        self,
        params: dict[str, Any],
        *,
        original_params: dict[str, Any],
        term_loader: Any = None,
        execution_steps: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
        """处理操作类动作的必填/术语/确认缓存逻辑。"""
        user_confirmed = _coerce_confirm_flag(params.pop(_OPERATION_CONFIRM_PARAM, False))
        for alias in _OPERATION_CONFIRM_PARAM_ALIASES:
            if alias != _OPERATION_CONFIRM_PARAM:
                params.pop(alias, None)

        missing_required = [
            {
                "param_code": param.param_code,
                "param_name": param.param_name or param.param_code,
            }
            for param in self._action.params
            if param.direction in ("IN", "INOUT")
            and param.required
            and _is_missing_required_value(params.get(param.param_code))
        ]
        await self._record_operation_step(
            execution_steps,
            step="param_validation",
            title="参数校验",
            status="failed" if missing_required else "completed",
            data={"missing_required_params": _safe_copy(missing_required)},
        )

        resolved_params, term_errors = await self._resolve_operation_terms(
            params,
            term_loader=term_loader,
        )
        await self._record_operation_step(
            execution_steps,
            step="term_resolved",
            title="术语转换",
            status="failed" if term_errors else ("skipped" if term_loader is None else "completed"),
            data={
                "params": _safe_copy(resolved_params),
                "term_errors": _safe_copy(term_errors),
            }
            if term_loader is not None
            else {"reason": "term_loader_not_configured"},
        )

        if missing_required or term_errors:
            self._clear_cached_operation_confirmation()
            message = self._build_operation_feedback_message(
                missing_required=missing_required,
                term_errors=term_errors,
                confirmation_state="validation_failed",
            )
            await self._record_operation_step(
                execution_steps,
                step="user_confirmation",
                title="用户确认",
                status="waiting",
                data={"cache_status": "cleared", "user_confirmed": user_confirmed},
            )
            return (
                await self._build_operation_ask_user_response(
                    message=message,
                    original_params=original_params,
                    normalized_params=params,
                    resolved_params=resolved_params,
                    missing_required=missing_required,
                    term_errors=term_errors,
                    user_confirmed=user_confirmed,
                    cache_status="validation_failed",
                    execution_steps=execution_steps,
                ),
                {},
                {
                    "submitted_params": _safe_copy(original_params),
                    "normalized_params": _safe_copy(params),
                    "resolved_params": _safe_copy(resolved_params),
                    "confirmation": {
                        "user_confirmed": user_confirmed,
                        "cache_status": "validation_failed",
                    },
                },
            )

        cached = self._get_cached_operation_confirmation()
        if not user_confirmed:
            self._set_cached_operation_confirmation(resolved_params)
            await self._record_operation_step(
                execution_steps,
                step="user_confirmation",
                title="用户确认",
                status="waiting",
                data={"cache_status": "cached", "user_confirmed": False},
            )
            return (
                await self._build_operation_ask_user_response(
                    message=self._build_operation_feedback_message(
                        missing_required=[],
                        term_errors=[],
                        confirmation_state="pending_confirmation",
                    ),
                    original_params=original_params,
                    normalized_params=params,
                    resolved_params=resolved_params,
                    missing_required=[],
                    term_errors=[],
                    user_confirmed=False,
                    cache_status="cached",
                    execution_steps=execution_steps,
                ),
                {},
                {
                    "submitted_params": _safe_copy(original_params),
                    "normalized_params": _safe_copy(params),
                    "resolved_params": _safe_copy(resolved_params),
                    "confirmation": {
                        "user_confirmed": False,
                        "cache_status": "cached",
                    },
                },
            )

        if cached is None:
            self._set_cached_operation_confirmation(resolved_params)
            await self._record_operation_step(
                execution_steps,
                step="user_confirmation",
                title="用户确认",
                status="waiting",
                data={"cache_status": "confirm_without_cache", "user_confirmed": True},
            )
            return (
                await self._build_operation_ask_user_response(
                    message=self._build_operation_feedback_message(
                        missing_required=[],
                        term_errors=[],
                        confirmation_state="confirm_without_cache",
                    ),
                    original_params=original_params,
                    normalized_params=params,
                    resolved_params=resolved_params,
                    missing_required=[],
                    term_errors=[],
                    user_confirmed=True,
                    cache_status="confirm_without_cache",
                    execution_steps=execution_steps,
                ),
                {},
                {
                    "submitted_params": _safe_copy(original_params),
                    "normalized_params": _safe_copy(params),
                    "resolved_params": _safe_copy(resolved_params),
                    "confirmation": {
                        "user_confirmed": True,
                        "cache_status": "confirm_without_cache",
                    },
                },
            )

        if cached != resolved_params:
            self._set_cached_operation_confirmation(resolved_params)
            await self._record_operation_step(
                execution_steps,
                step="user_confirmation",
                title="用户确认",
                status="waiting",
                data={"cache_status": "confirm_mismatch", "user_confirmed": True},
            )
            return (
                await self._build_operation_ask_user_response(
                    message=self._build_operation_feedback_message(
                        missing_required=[],
                        term_errors=[],
                        confirmation_state="confirm_mismatch",
                    ),
                    original_params=original_params,
                    normalized_params=params,
                    resolved_params=resolved_params,
                    missing_required=[],
                    term_errors=[],
                    user_confirmed=True,
                    cache_status="confirm_mismatch",
                    execution_steps=execution_steps,
                ),
                {},
                {
                    "submitted_params": _safe_copy(original_params),
                    "normalized_params": _safe_copy(params),
                    "resolved_params": _safe_copy(resolved_params),
                    "confirmation": {
                        "user_confirmed": True,
                        "cache_status": "confirm_mismatch",
                    },
                },
            )

        self._clear_cached_operation_confirmation()
        await self._record_operation_step(
            execution_steps,
            step="user_confirmation",
            title="用户确认",
            status="completed",
            data={"cache_status": "confirmed", "user_confirmed": True},
        )
        return (
            None,
            resolved_params,
            {
                "submitted_params": _safe_copy(original_params),
                "normalized_params": _safe_copy(params),
                "resolved_params": _safe_copy(resolved_params),
                "confirmation": {
                    "user_confirmed": True,
                    "cache_status": "confirmed",
                },
            },
        )

    async def execute(self, params: dict[str, object]) -> dict[str, object]:
        """
        执行动作

        完整的执行流程：
        1. 参数映射：将参数名/别名转换为标准 param_code
        2. 术语解析：解析业务术语到实际值
        3. 执行操作：按优先级选择执行方式（虚拟查询/脚本/API）
        4. 结果标准化：统一返回格式

        Args:
            params: 执行参数字典

        Returns:
            dict: 标准化的执行结果，包含 records, total, meta 等字段

        Raises:
            ActionNotConfiguredError: 动作未配置执行方式
        """
        from datacloud_data_sdk.exceptions import ActionNotConfiguredError

        params = dict(params)
        original_params = _safe_copy(params)
        term_loader = getattr(self._loader._config, "term_loader", None) if self._loader else None
        include_execution_steps = self._should_include_execution_steps()
        execution_steps: list[dict[str, Any]] | None = [] if include_execution_steps else None
        operation_result_extra: dict[str, Any] = {}

        from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
        from datacloud_data_sdk.result_formatter import build_query_response

        cfg = self._loader._config if self._loader else None
        threshold = cfg.query_result_csv_threshold if cfg else 0
        csv_manager = CsvStorageManager(
            cfg.csv_base_dir if cfg else "/tmp/datacloud_csv",
            result_file_storage=getattr(cfg, "result_file_storage", None),
        )

        request_received_data = {
            "action_code": self._action.action_code,
            "action_name": self._action.action_name or self._action.action_code,
            "params": params,
        }
        _append_execution_step(
            execution_steps,
            step="request_received",
            title="接收动作请求",
            data=request_received_data,
        )
        await _emit_execution_step(
            step="request_received",
            title="接收动作请求",
            data=request_received_data,
        )

        if getattr(self._action, "is_virtual", False):
            action_executing_data = self._describe_execution_mode()
            _append_execution_step(
                execution_steps,
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            await _emit_execution_step(
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            result = await self._execute_virtual(
                params,
                term_loader=term_loader,
                execution_steps=execution_steps,
            )
            normalized = self._normalize_to_unified_format(result)
            normalized = await self._attach_execution_steps(normalized, execution_steps)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
            )

        mapped_params = self._normalize_input_params(params)
        param_mapping_data = {
            "params": mapped_params,
            "changed": mapped_params != params,
        }
        _append_execution_step(
            execution_steps,
            step="param_mapping",
            title="参数映射",
            data=param_mapping_data,
        )
        await _emit_execution_step(
            step="param_mapping",
            title="参数映射",
            data=param_mapping_data,
        )

        params = mapped_params
        if self._is_confirmable_operation():
            (
                ask_user_response,
                prepared_params,
                operation_result_extra,
            ) = await self._prepare_confirmable_operation(
                dict(params),
                original_params=original_params
                if isinstance(original_params, dict)
                else {"value": original_params},
                term_loader=term_loader,
                execution_steps=execution_steps,
            )
            if ask_user_response is not None:
                return ask_user_response
            params = prepared_params
        elif term_loader:
            from datacloud_data_sdk.plan.term_resolver import TermResolver

            resolved_params = TermResolver(term_loader).resolve(self._action, params)
            term_resolved_data = {
                "params": resolved_params,
                "changed": resolved_params != params,
            }
            _append_execution_step(
                execution_steps,
                step="term_resolved",
                title="术语转换",
                data=term_resolved_data,
            )
            await _emit_execution_step(
                step="term_resolved",
                title="术语转换",
                data=term_resolved_data,
            )
            params = resolved_params
        else:
            skipped_term_data = {"reason": "term_loader_not_configured"}
            _append_execution_step(
                execution_steps,
                step="term_resolved",
                title="术语转换",
                status="skipped",
                data=skipped_term_data,
            )
            await _emit_execution_step(
                step="term_resolved",
                title="术语转换",
                status="skipped",
                data=skipped_term_data,
            )

        if self._action.script:
            action_executing_data = self._describe_execution_mode()
            _append_execution_step(
                execution_steps,
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            await _emit_execution_step(
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            result = await self._execute_script(params)
            normalized = self._normalize_to_unified_format(result)
            normalized.update(operation_result_extra)
            normalized = await self._attach_execution_steps(normalized, execution_steps)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
            )
        if self._action.function_refs:
            action_executing_data = self._describe_execution_mode()
            _append_execution_step(
                execution_steps,
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            await _emit_execution_step(
                step="action_executing",
                title="动作执行",
                data=action_executing_data,
            )
            result = await self._execute_api(params)
            normalized = self._normalize_to_unified_format(result)
            normalized.update(operation_result_extra)
            normalized = await self._attach_execution_steps(normalized, execution_steps)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
            )
        raise ActionNotConfiguredError(self._action.action_code)

    async def _execute_virtual(
        self,
        params: dict[str, Any],
        *,
        term_loader: Any = None,
        execution_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        执行虚拟查询动作

        根据 action_family 路由到对应执行器：
        - lookup → LookupExecutor（新协议）
        - analyze → AnalyzeExecutor（新协议）
        - search → KbSearchExecutor（新协议）
        - 无 action_family 或旧 query_* → DynamicQueryExecutor（兼容旧协议）

        Args:
            params: 查询参数

        Returns:
            dict: 包含 records 和 total 的原始结果

        Raises:
            ActionNotConfiguredError: 未配置 loader 时抛出
        """
        from datacloud_data_sdk.executor.dynamic_query_executor import DynamicQueryExecutor

        if not self._loader:
            from datacloud_data_sdk.exceptions import ActionNotConfiguredError

            raise ActionNotConfiguredError(self._action.action_code)

        scope_code = (
            getattr(self._action, "scope_code", "")
            or getattr(self._action, "belong_class", "")
            or ""
        )
        action_family = getattr(self._action, "action_family", None)
        scope_type = getattr(self._action, "scope_type", "object")
        required_filter_groups = self._get_virtual_required_filter_groups()

        # 视图级虚拟动作：路由到 ViewLookupExecutor / ViewAnalyzeExecutor
        if scope_type == "view":
            try:
                view = self._loader.get_view(scope_code)
            except Exception:
                return {
                    "records": [],
                    "total": 0,
                    "meta": {"view_id": scope_code, "note": "view not found"},
                }
            params = await self._prepare_virtual_params(
                params,
                self._build_view_runtime_fields(view),
                action_family,
                required_filter_groups,
                term_loader=term_loader,
                execution_steps=execution_steps,
            )
            return await self._execute_virtual_view(view, action_family, params)

        object_code = scope_code
        cls = self._loader.get_ontology_class(object_code)
        params = await self._prepare_virtual_params(
            params,
            list(getattr(cls, "fields", [])),
            action_family,
            required_filter_groups,
            term_loader=term_loader,
            execution_steps=execution_steps,
        )

        # 对象级虚拟动作：按 action_family 路由
        if action_family == "query":
            from datacloud_data_sdk.executor.query_executor import QueryExecutor

            return await QueryExecutor(self._loader).execute(object_code, params)

        if action_family == "compute":
            from datacloud_data_sdk.executor.compute_executor import ComputeExecutor

            return await ComputeExecutor(self._loader).execute(object_code, params)

        if action_family == "lookup":
            from datacloud_data_sdk.executor.lookup_executor import LookupExecutor

            return await LookupExecutor(self._loader).execute(object_code, params)

        if action_family == "analyze":
            from datacloud_data_sdk.executor.analyze_executor import AnalyzeExecutor

            return await AnalyzeExecutor(self._loader).execute(object_code, params)

        if action_family == "search":
            from datacloud_data_sdk.executor.kb_search_executor import KbSearchExecutor

            return await KbSearchExecutor(self._loader).execute(object_code, params)

        # 兼容旧协议（query_* 动作 / 无 action_family）

        return await DynamicQueryExecutor(self._loader).execute(object_code, params)

    async def _execute_virtual_view(
        self, view: Any, action_family: str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        """执行视图级虚拟动作（路由到 ViewLookupExecutor / ViewAnalyzeExecutor）。

        query/compute 动作的 params 使用中文名，进入 View 执行器前先翻译成 property_code。
        """
        try:
            from datacloud_data_sdk.executor.view_analyze_executor import ViewAnalyzeExecutor
            from datacloud_data_sdk.executor.view_lookup_executor import ViewLookupExecutor
        except ImportError:
            return {
                "records": [],
                "total": 0,
                "meta": {"view_id": view.view_id, "note": "view executor not available"},
            }

        if action_family in ("query", "lookup"):
            if action_family == "query":
                params = _translate_view_params(view, params)
            return await ViewLookupExecutor(self._loader).execute(view, params)

        if action_family in ("compute", "analyze"):
            if action_family == "compute":
                params = _translate_view_params(view, params)
            return await ViewAnalyzeExecutor(self._loader).execute(view, params)

        return {"records": [], "total": 0, "meta": {"view_id": view.view_id}}

    async def _prepare_virtual_params(
        self,
        params: dict[str, Any],
        fields: list[Any],
        action_family: str | None,
        required_filter_groups: list[str],
        *,
        term_loader: Any = None,
        execution_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """执行前统一处理虚拟动作参数。"""
        prepared = dict(params)
        if term_loader and "filters" in prepared:
            from datacloud_data_sdk.plan.term_resolver import TermResolver

            original_filters = _safe_copy(prepared["filters"])
            prepared["filters"] = TermResolver(term_loader).resolve_filter_values(
                prepared["filters"], fields
            )
            term_resolved_data = {
                "scope": "filters",
                "params": {"filters": prepared["filters"]},
                "changed": prepared["filters"] != original_filters,
            }
            _append_execution_step(
                execution_steps,
                step="term_resolved",
                title="术语转换",
                data=term_resolved_data,
            )
            await _emit_execution_step(
                step="term_resolved",
                title="术语转换",
                data=term_resolved_data,
            )
        else:
            skipped_term_data = {"reason": "no_term_bound_filters"}
            _append_execution_step(
                execution_steps,
                step="term_resolved",
                title="术语转换",
                status="skipped",
                data=skipped_term_data,
            )
            await _emit_execution_step(
                step="term_resolved",
                title="术语转换",
                status="skipped",
                data=skipped_term_data,
            )

        if action_family in ("lookup", "analyze"):
            from datacloud_data_sdk.virtual_action.validator import VirtualActionValidator

            validator = VirtualActionValidator(fields)
            if action_family == "lookup":
                validator.validate_lookup(prepared, required_filter_groups)
            else:
                validator.validate_analyze(prepared, required_filter_groups)
        return prepared

    def _should_include_execution_steps(self) -> bool:
        """是否在动作返回中附带 execution_steps。"""
        from datacloud_data_sdk.context import get_tool_call_detail

        return get_tool_call_detail()

    def _describe_execution_mode(self) -> dict[str, Any]:
        """返回当前动作的执行模式摘要。"""
        if getattr(self._action, "is_virtual", False):
            return {
                "mode": "virtual",
                "action_family": getattr(self._action, "action_family", None),
                "scope_type": getattr(self._action, "scope_type", "object"),
                "scope_code": getattr(self._action, "scope_code", ""),
            }
        if self._action.script:
            return {
                "mode": "script",
                "action_family": getattr(self._action, "action_family", None),
            }
        if self._action.function_refs:
            return {
                "mode": "api",
                "action_family": getattr(self._action, "action_family", None),
                "function_code": self._action.function_refs[0],
            }
        return {"mode": "unconfigured"}

    async def _attach_execution_steps(
        self,
        normalized: dict[str, Any],
        execution_steps: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """为动作结果补充 execution_steps 明细。"""
        if execution_steps is None:
            return normalized

        records = normalized.get("records")
        record_count = len(records) if isinstance(records, list) else 0
        meta = normalized.get("meta", {})
        columns = meta.get("columns", []) if isinstance(meta, dict) else []
        action_completed_data = {
            "record_count": record_count,
            "total": normalized.get("total", record_count),
            "columns": columns,
        }
        _append_execution_step(
            execution_steps,
            step="action_completed",
            title="动作执行完成",
            data=action_completed_data,
        )
        await _emit_execution_step(
            step="action_completed",
            title="动作执行完成",
            data=action_completed_data,
        )

        normalized["execution_steps"] = execution_steps
        return normalized

    def _get_virtual_required_filter_groups(self) -> list[str]:
        """获取虚拟动作的强制过滤组列表。"""
        schema = getattr(self._action, "input_schema", None) or {}
        groups = schema.get("x-dc-required-filter-group", [])
        if isinstance(groups, list):
            return [str(item) for item in groups]
        return []

    def _build_view_runtime_fields(self, view: Any) -> list[OntologyField]:
        """基于视图字段和源对象字段构建可用于校验/术语解析的运行时字段。"""
        runtime_fields: list[OntologyField] = []
        source_field_cache: dict[str, Any] = {}

        for view_field in getattr(view, "fields", []):
            property_code = getattr(view_field, "property_code", "")
            if not property_code:
                continue
            source_key = (
                f"{getattr(view_field, 'source_object_code', '')}"
                f":{getattr(view_field, 'source_object_column_code', '')}"
            )
            if source_key not in source_field_cache:
                source_field_cache[source_key] = self._find_source_field(
                    getattr(view_field, "source_object_code", ""),
                    getattr(view_field, "source_object_column_code", ""),
                )
            source_field = source_field_cache[source_key]
            runtime_fields.append(
                OntologyField(
                    field_code=property_code,
                    field_name=getattr(view_field, "property_name", property_code),
                    field_type=(
                        getattr(view_field, "field_type", None)
                        or getattr(source_field, "field_type", None)
                        or "STRING"
                    ),
                    description=getattr(source_field, "description", ""),
                    aliases=list(getattr(source_field, "aliases", [])),
                    required=getattr(source_field, "required", False),
                    is_primary_key=getattr(source_field, "is_primary_key", False),
                    source_column=(
                        getattr(view_field, "source_object_column_code", None)
                        or getattr(source_field, "source_column", None)
                    ),
                    term_set=getattr(source_field, "term_set", None),
                    term_type=getattr(source_field, "term_type", None),
                    term_field=getattr(source_field, "term_field", None),
                    dataset_id=getattr(source_field, "dataset_id", None),
                    physical_mappings=list(getattr(source_field, "physical_mappings", [])),
                    property_kind=getattr(source_field, "property_kind", "physical"),
                    derived_config=getattr(source_field, "derived_config", None),
                    relation_ref=getattr(source_field, "relation_ref", None),
                    resolve_action_code=getattr(source_field, "resolve_action_code", None),
                    resolve_param_binding=getattr(source_field, "resolve_param_binding", None),
                    analytic_role=(
                        getattr(view_field, "analytic_role", None)
                        or getattr(source_field, "analytic_role", None)
                    ),
                    analytic_kind=(
                        getattr(view_field, "analytic_kind", None)
                        or getattr(source_field, "analytic_kind", None)
                    ),
                    secondary_role=getattr(source_field, "secondary_role", None),
                    filter_ops=list(
                        getattr(view_field, "filter_ops", None)
                        or getattr(source_field, "filter_ops", [])
                    ),
                    group_ops=list(
                        getattr(view_field, "group_ops", None)
                        or getattr(source_field, "group_ops", [])
                    ),
                    aggregate_ops=list(
                        getattr(view_field, "aggregate_ops", None)
                        or getattr(source_field, "aggregate_ops", [])
                    ),
                    required_filter_group=(
                        getattr(view_field, "required_filter_group", None)
                        or getattr(source_field, "required_filter_group", None)
                    ),
                )
            )

        if runtime_fields:
            return runtime_fields

        runtime_fields.extend(
            OntologyField(
                field_code=field.field_code,
                field_name=field.field_name,
                field_type=field.field_type,
                description=field.description,
                aliases=list(field.aliases),
                required=field.required,
                is_primary_key=field.is_primary_key,
                source_column=field.source_column,
                term_set=field.term_set,
                term_type=field.term_type,
                term_field=field.term_field,
                dataset_id=field.dataset_id,
                physical_mappings=list(field.physical_mappings),
                property_kind=field.property_kind,
                derived_config=field.derived_config,
                relation_ref=field.relation_ref,
                resolve_action_code=field.resolve_action_code,
                resolve_param_binding=field.resolve_param_binding,
                analytic_role=field.analytic_role,
                analytic_kind=field.analytic_kind,
                secondary_role=field.secondary_role,
                filter_ops=list(field.filter_ops),
                group_ops=list(field.group_ops),
                aggregate_ops=list(field.aggregate_ops),
                required_filter_group=field.required_filter_group,
            )
            for obj in getattr(view, "objects", [])
            for field in getattr(obj._cls, "fields", [])
        )
        return runtime_fields

    def _find_source_field(self, object_code: str, source_column_code: str) -> Any | None:
        """从源对象中查找视图字段映射对应的字段定义。"""
        if not object_code or not source_column_code:
            return None
        try:
            cls = self._loader.get_ontology_class(object_code)
        except Exception:
            return None

        for field in getattr(cls, "fields", []):
            if field.field_code == source_column_code or field.source_column == source_column_code:
                return field
        return None

    async def _execute_script(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        执行脚本动作

        通过 ScriptExecutor 执行预定义的脚本代码，
        支持从返回结果中提取记录数据。

        Args:
            params: 脚本执行参数

        Returns:
            dict: 标准化的结果格式
        """
        from datacloud_data_sdk.executor.script_executor import ScriptExecutor

        executor = ScriptExecutor(ontology_loader=self._loader)
        result = await executor.execute(
            self._action.script,  # type: ignore[arg-type]
            params,
            action_code=self._action.action_code,
        )
        if not isinstance(result, dict):
            return {
                "records": [],
                "total": 0,
                "meta": {"viewId": "auto_view", "columns": [], "total": 0},
            }
        out_params = [
            (p.param_code, p.mapping_path)
            for p in self._action.params
            if getattr(p, "direction", "IN") in ("OUT", "INOUT") and getattr(p, "mapping_path", "")
        ]
        if out_params:
            from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path

            records = extract_by_mapping_path(result, out_params)
            columns = [p[0] for p in out_params]
        else:
            records = self._extract_records_fallback(result)
            columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": len(records),
            "meta": {"viewId": "auto_view", "columns": columns, "total": len(records)},
        }

    async def _execute_api(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        通过 HTTP API 执行动作

        调用外部 API 服务执行动作，支持：
        - 自动构建请求 URL 和 headers
        - 请求日志记录（curl 格式）
        - 响应数据提取和标准化

        Args:
            params: API 请求参数

        Returns:
            dict: 标准化的结果格式

        Raises:
            ActionNotConfiguredError: 未配置 function 或 loader
            ApiExecutionError: API 调用失败时抛出
        """
        import httpx

        from datacloud_data_sdk.exceptions import ActionNotConfiguredError, ApiExecutionError
        from datacloud_data_sdk.utils.curl_logger import log_curl

        if not self._loader:
            raise ActionNotConfiguredError(self._action.action_code)

        function_code = self._action.function_refs[0]
        config = self._loader.get_function_config(function_code)
        if not config:
            raise ActionNotConfiguredError(self._action.action_code)

        method, path_template = self._get_request_target(config)
        request_parts = self._build_request_parts(params, method=method)
        url = self._build_url(
            config,
            path_template=path_template,
            path_params=request_parts["path"],
        )
        headers = self._build_headers(request_parts["headers"])

        log_curl(
            method,
            url,
            headers=headers,
            body=request_parts["body"] if request_parts["body"] else None,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            request_kwargs: dict[str, Any] = {"headers": headers}
            if request_parts["query"]:
                request_kwargs["params"] = request_parts["query"]
            if request_parts["body"] is not None:
                request_kwargs["json"] = request_parts["body"]
            resp = await client.request(method, url, **request_kwargs)

        if resp.status_code >= 400:
            raise ApiExecutionError(function_code, resp.status_code, resp.text)

        raw = resp.json()
        out_params = [
            (p.param_code, p.mapping_path)
            for p in self._action.params
            if getattr(p, "direction", "IN") in ("OUT", "INOUT") and getattr(p, "mapping_path", "")
        ]
        if out_params:
            from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path

            records = extract_by_mapping_path(raw, out_params)
            columns = [p[0] for p in out_params]
        else:
            records = self._extract_records_fallback(raw)
            columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": len(records),
            "meta": {"viewId": "auto_view", "columns": columns, "total": len(records)},
        }

    def _get_request_target(self, config: dict[str, Any]) -> tuple[str, str]:
        """从 function config 解析 HTTP method 与 path。"""
        paths = config.get("paths", {})
        path_template, operations = next(iter(paths.items()), ("", {}))
        if not isinstance(operations, dict):
            return "POST", path_template
        method = next(iter(operations.keys()), "post").upper()
        return method, path_template

    def _build_request_parts(self, params: dict[str, Any], *, method: str) -> dict[str, Any]:
        """根据动作 mapping_path 将参数拆分为 path/query/body/header。"""
        result: dict[str, Any] = {
            "path": {},
            "query": {},
            "body": None,
            "headers": {},
        }
        default_location = "query" if method.upper() in {"GET", "DELETE", "HEAD"} else "body"
        for param in self._action.params:
            if getattr(param, "direction", "IN") not in ("IN", "INOUT"):
                continue
            value = params.get(param.param_code)
            if value is None and param.default_value is not None:
                value = param.default_value
            if value is None:
                continue
            location, path_parts = _parse_mapping_path(
                getattr(param, "mapping_path", ""),
                default_location=default_location,
            )
            if location == "body":
                if path_parts:
                    result["body"] = _assign_runtime_path(result["body"], path_parts, value)
                else:
                    if not isinstance(result["body"], dict):
                        result["body"] = {}
                    result["body"][param.param_code] = value
                continue

            key = self._resolve_request_key(path_parts, param.param_code)
            result[location][key] = value
        return result

    @staticmethod
    def _resolve_request_key(
        path_parts: list[str],
        fallback_key: str,
    ) -> str:
        """为 query/path/header 解析最终物理字段名。"""
        if not path_parts:
            return fallback_key
        key = path_parts[-1]
        if key == "[]":
            return fallback_key
        return key.removesuffix("[]")

    def _build_url(
        self,
        config: dict[str, Any],
        *,
        path_template: str | None = None,
        path_params: dict[str, Any] | None = None,
    ) -> str:
        servers = config.get("servers", [])
        base_url = servers[0]["url"] if servers else "http://localhost:8080"
        paths = config.get("paths", {})
        path = path_template if path_template is not None else next(iter(paths), "")
        for key, value in (path_params or {}).items():
            encoded = quote(str(value), safe="")
            path = path.replace(f"{{{key}}}", encoded)
            path = path.replace(f":{key}", encoded)
        return f"{base_url}{path}"

    def _build_headers(self, extra_headers: dict[str, Any] | None = None) -> dict[str, str]:
        from datacloud_data_sdk.context import get_current_context

        headers: dict[str, str] = {"Content-Type": "application/json"}
        try:
            ctx = get_current_context()
            if ctx.token:
                headers["Authorization"] = f"Bearer {ctx.token}"
            if ctx.tenant_id:
                headers["X-Tenant-Id"] = ctx.tenant_id
        except Exception as exc:
            logger.debug("_build_headers: failed to inject auth context: %s", exc)
        for key, value in (extra_headers or {}).items():
            headers[str(key)] = str(value)
        return headers

    def _extract_records_fallback(self, data: Any) -> list[dict[str, Any]]:
        """从 API 原始响应按常见 key 兜底提取 records。"""
        if isinstance(data, list):
            return data if data and isinstance(data[0], dict) else [{"value": data}] if data else []
        if isinstance(data, dict):
            for key in ("data", "records", "items", "list", "users", "results", "opportunities"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
        return [{"value": data}]

    def _normalize_to_unified_format(self, result: dict[str, Any]) -> dict[str, Any]:
        """将任意 dict 归一化为 {records, total, meta} 统一结构。"""
        if not isinstance(result, dict):
            return {
                "records": [],
                "total": 0,
                "meta": {"viewId": "auto_view", "columns": [], "total": 0},
            }
        if "records" in result and "meta" in result:
            meta = result.get("meta", {})
            meta.setdefault("viewId", "auto_view")
            meta.setdefault("total", result.get("total", len(result.get("records", []))))
            return result
        records = result.get("records")
        if records is None:
            records = [result] if result else []
        if not isinstance(records, list):
            records = [result]
        total = len(records)
        columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": total,
            "meta": {"viewId": "auto_view", "columns": columns, "total": total},
        }
