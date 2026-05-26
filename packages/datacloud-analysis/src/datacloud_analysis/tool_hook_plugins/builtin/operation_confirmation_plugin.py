"""Built-in hook plugin for operation action confirmation forms."""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from typing import Any

from datacloud_analysis.tool_hook_plugins.types import (
    ClarificationNeededError,
    HookContext,
    HookDecision,
)

PLUGIN_ID = "builtin.operation_confirmation"
PRIORITY = 150
ENABLED = True

_INTERRUPT_TYPE = "operation_form"
_CONFIRM_PARAM = "userConfirmed"
_OPERATION_CONFIRM_PARAM = "_operationConfirm"
_OPERATION_FAMILIES = frozenset({"insert", "update", "delete", "write", "operation"})
_INPUT_DIRECTIONS = frozenset({"IN", "INOUT", ""})
_IGNORED_SCHEMA_FIELDS = frozenset({_CONFIRM_PARAM, _OPERATION_CONFIRM_PARAM})
_DISPLAY_WRAPPER_FIELDS = frozenset({"requestBody", "body", "parameters"})
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
_LOCATION_SCHEMA_KEYS: dict[str, str] = {
    "body": "requestBody",
    "query": "query",
    "path": "path",
    "headers": "headers",
}

logger = logging.getLogger(__name__)


async def before_call_back(ctx: HookContext) -> HookDecision | None:
    """Interrupt operation tool calls before execution and resume with confirmed params."""
    tool_name = str(ctx.get("tool_name") or "")
    tool_params = dict(ctx.get("tool_params") or {})
    metadata = dict(ctx.get("metadata") or {})
    state = metadata.get("state")
    state_dict = state if isinstance(state, dict) else {}
    action = find_operation_action(metadata.get("loader"), tool_name)
    if action is None:
        return None

    formatted_params = _get_operation_formatted_params(state_dict, tool_name)
    if formatted_params is not None:
        if not bool(formatted_params.get("confirmed")):
            return {
                "action": "fail",
                "result": {
                    "tool_error": {
                        "error_type": "OperationCancelled",
                        "message": str(formatted_params.get("reason") or "用户取消操作"),
                        "retryable": False,
                        "hint": "用户已取消本次操作，不再执行业务提交。",
                        "context": {"tool_name": tool_name},
                    }
                },
            }
        patched = dict(formatted_params.get("params") or {})
        if not patched:
            patched = restore_action_params(
                list(formatted_params.get("rule") or []),
                action=action,
                original_params=tool_params,
            )
        patched[_CONFIRM_PARAM] = True
        patched[_OPERATION_CONFIRM_PARAM] = {
            "formId": str(formatted_params.get("formId") or ""),
            "confirmed": True,
        }
        logger.info("[operation_confirmation] resume patch tool=%s", tool_name)
        return {"action": "patch", "patch": {"tool_params": patched}}

    operation_form = build_operation_form(action, tool_params)
    form_id = str(operation_form.get("formId") or "")
    logger.info("[operation_confirmation] interrupt tool=%s form_id=%s", tool_name, form_id)
    raise ClarificationNeededError(
        {
            "interrupt_type": _INTERRUPT_TYPE,
            "tool_name": tool_name,
            "structured_input": deepcopy(tool_params),
            "operation_form": operation_form,
            "operation_confirm_context": {
                "formId": form_id,
                "actionCode": str(getattr(action, "action_code", tool_name) or tool_name),
                "originalParamsHash": _stable_hash(tool_params),
            },
        }
    )


def find_operation_action(loader: Any, tool_name: str) -> Any | None:
    """Find a confirmable ontology action by tool name."""
    if loader is None or not tool_name:
        return None
    for scope, action in _iter_loader_actions(loader):
        action_code = str(getattr(action, "action_code", "") or "")
        aliases = [str(item) for item in (getattr(action, "legacy_aliases", None) or [])]
        if tool_name not in {action_code, *aliases}:
            continue
        if _is_confirmable_action(action):
            try:
                action._datacloud_scope = scope
            except Exception:
                logger.debug("failed to attach action scope metadata", exc_info=True)
            return action
    return None


def build_operation_form(action: Any, tool_params: dict[str, Any]) -> dict[str, Any]:
    """Build frontend operation confirmation form from action metadata and params."""
    form_id = _build_form_id(action, tool_params)
    action_code = str(getattr(action, "action_code", "") or "")
    action_name = str(getattr(action, "action_name", "") or action_code)
    rule = _build_top_level_rule(action, tool_params, form_id=form_id)
    return {
        "schemaVersion": "1.0",
        "formId": form_id,
        "actionCode": action_code,
        "actionName": action_name,
        "title": f"确认执行：{action_name or action_code}",
        "description": "请确认以下表单信息，确认后将继续执行。",
        "rule": rule,
    }


def restore_action_params(
    rule: list[Any],
    *,
    action: Any | None = None,
    original_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Restore action params from confirmed 2D rule payload."""
    rule_rows = _normalize_rule_rows(rule)
    if not rule_rows:
        return dict(original_params or {})

    action_family = str(getattr(action, "action_family", "") or "").lower() if action else ""
    if action_family == "insert":
        return {"records": [_fields_to_object(row) for row in rule_rows]}

    params: dict[str, Any] = dict(original_params or {})
    if len(rule_rows) == 1:
        for key, value in _fields_to_object(rule_rows[0], use_field_path=True).items():
            _set_path_value(params, key, value)
        return _filter_restored_params(params, action)

    params["records"] = [_fields_to_object(row, use_field_path=True) for row in rule_rows]
    return _filter_restored_params(params, action)


def _get_operation_formatted_params(
    state: dict[str, Any],
    tool_name: str,
) -> dict[str, Any] | None:
    formatted = state.get("clarification_formatted_params")
    if not isinstance(formatted, dict):
        return None
    if str(formatted.get("interrupt_type") or "") != _INTERRUPT_TYPE:
        return None
    if str(formatted.get("tool_name") or "") != tool_name:
        return None
    return formatted


def _iter_loader_actions(loader: Any) -> list[tuple[Any, Any]]:
    actions: list[tuple[Any, Any]] = []
    get_classes = getattr(loader, "get_ontology_classes", None)
    if callable(get_classes):
        try:
            for cls in get_classes():
                actions.extend((cls, action) for action in list(getattr(cls, "actions", []) or []))
        except Exception:
            logger.debug("operation action lookup failed for ontology classes", exc_info=True)
    get_views = getattr(loader, "get_views", None)
    if callable(get_views):
        try:
            for view in get_views():
                actions.extend(
                    (view, action) for action in list(getattr(view, "actions", []) or [])
                )
        except Exception:
            logger.debug("operation action lookup failed for views", exc_info=True)
    return actions


def _is_confirmable_action(action: Any) -> bool:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    action_family = str(getattr(action, "action_family", "") or "").lower()
    return action_type == "operation" or action_family in _OPERATION_FAMILIES


def _build_top_level_rule(
    action: Any,
    tool_params: dict[str, Any],
    *,
    form_id: str,
) -> list[list[dict[str, Any]]]:
    action_family = str(getattr(action, "action_family", "") or "").lower()
    field_meta = _action_field_meta(action)
    param_meta = _action_param_meta(action)
    if action_family == "insert" and isinstance(tool_params.get("records"), list):
        return [
            _build_fields_from_schema(
                _get_records_item_schema(action),
                record if isinstance(record, dict) else {},
                item_id=_build_item_id(form_id, index),
                field_meta=field_meta,
                param_meta=param_meta,
            )
            for index, record in enumerate(tool_params.get("records") or [], start=1)
        ]

    schema, values, parent_path = _display_schema_and_values(
        _get_action_input_schema(action),
        tool_params,
    )
    row = _build_fields_from_schema(
        schema,
        values,
        item_id=_build_item_id(form_id, 1),
        parent_path=parent_path,
        field_meta=field_meta,
        param_meta=param_meta,
    )
    if row:
        return [row]

    params = [
        param
        for param in list(getattr(action, "params", []) or [])
        if str(getattr(param, "direction", "") or "").upper() in _INPUT_DIRECTIONS
    ]
    return [
        [
            _build_field_from_param(param, tool_params, first=index == 1, form_id=form_id)
            for index, param in enumerate(params, start=1)
        ]
    ]


def _get_action_input_schema(action: Any) -> dict[str, Any]:
    schema = getattr(action, "input_schema", None)
    if isinstance(schema, dict):
        return schema
    params = [
        param
        for param in list(getattr(action, "params", []) or [])
        if str(getattr(param, "direction", "") or "").upper() in _INPUT_DIRECTIONS
    ]
    if any(str(getattr(param, "mapping_path", "") or "").startswith("$.") for param in params):
        return _build_input_schema_from_mapping_paths(params)
    return _build_flat_input_schema(params)


def _build_flat_input_schema(params: list[Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in params:
        code = str(getattr(param, "param_code", "") or "")
        if not code:
            continue
        properties[code] = {
            "type": _normalize_field_type(getattr(param, "param_type", "string")),
            "description": str(getattr(param, "param_name", "") or code),
        }
        term = _term_from_param(param)
        if term is not None:
            properties[code]["term"] = term
        if bool(getattr(param, "required", False)):
            required.append(code)
    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def _build_input_schema_from_mapping_paths(params: list[Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_wrappers: set[str] = set()
    properties = schema["properties"]
    for param in params:
        code = str(getattr(param, "param_code", "") or "")
        if not code:
            continue
        leaf_schema = _build_param_schema(param)
        location, path_parts = _parse_mapping_path(
            str(getattr(param, "mapping_path", "") or ""),
            default_location="body",
        )
        location_key = _schema_location_key(location)
        if not path_parts:
            path_parts = [code]

        node = properties.setdefault(location_key, {"type": "object", "properties": {}})
        if not isinstance(node, dict):
            node = {"type": "object", "properties": {}}
            properties[location_key] = node
        _assign_schema_path(
            node,
            path_parts,
            leaf_schema,
            required=bool(getattr(param, "required", False)),
        )
        if bool(getattr(param, "required", False)):
            required_wrappers.add(location_key)
    if required_wrappers:
        schema["required"] = sorted(required_wrappers)
    return schema


def _build_param_schema(param: Any) -> dict[str, Any]:
    code = str(getattr(param, "param_code", "") or "")
    schema: dict[str, Any] = {
        "type": _normalize_field_type(getattr(param, "param_type", "string")),
        "description": str(getattr(param, "param_name", "") or code),
    }
    term = _term_from_param(param)
    if term is not None:
        schema["term"] = term
    default_value = getattr(param, "default_value", None)
    if default_value is not None:
        schema["default"] = default_value
    return schema


def _get_records_item_schema(action: Any) -> dict[str, Any]:
    schema = _get_action_input_schema(action)
    records_schema = dict((schema.get("properties") or {}).get("records") or {})
    item_schema = records_schema.get("items")
    return item_schema if isinstance(item_schema, dict) else {"type": "object", "properties": {}}


def _display_schema_and_values(
    schema: dict[str, Any],
    values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict) or len(properties) != 1:
        return schema, values, ""
    wrapper_key = next(iter(properties))
    wrapper_schema = properties.get(wrapper_key)
    if wrapper_key not in _DISPLAY_WRAPPER_FIELDS or not isinstance(wrapper_schema, dict):
        return schema, values, ""
    if str(wrapper_schema.get("type") or "").lower() != "object":
        return schema, values, ""
    wrapper_values = values.get(wrapper_key)
    return (
        wrapper_schema,
        wrapper_values if isinstance(wrapper_values, dict) else values,
        wrapper_key,
    )


def _build_fields_from_schema(
    schema: dict[str, Any],
    values: dict[str, Any],
    *,
    item_id: str,
    parent_path: str = "",
    field_meta: dict[str, Any] | None = None,
    param_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = set(schema.get("required") or [])
    fields: list[dict[str, Any]] = []
    for code, property_schema_raw in properties.items():
        if code in _IGNORED_SCHEMA_FIELDS or not isinstance(property_schema_raw, dict):
            continue
        property_schema = dict(property_schema_raw)
        field_path = f"{parent_path}.{code}" if parent_path else str(code)
        field_type = _schema_field_type(property_schema)
        field_value = values.get(code)
        if field_value is None and "default" in property_schema:
            field_value = property_schema.get("default")
        children: list[list[dict[str, Any]]] | None = None
        if field_type == "object":
            child_values = field_value if isinstance(field_value, dict) else {}
            children = [
                _build_fields_from_schema(
                    property_schema,
                    child_values,
                    item_id=f"{item_id}_{code}_001",
                    parent_path=field_path,
                    field_meta=field_meta,
                    param_meta=param_meta,
                )
            ]
        elif field_type == "array" and _is_array_object_schema(property_schema):
            items_schema = property_schema.get("items")
            item_values = field_value if isinstance(field_value, list) else []
            if not item_values:
                item_values = [{}]
            children = [
                _build_fields_from_schema(
                    items_schema if isinstance(items_schema, dict) else {},
                    item if isinstance(item, dict) else {},
                    item_id=f"{item_id}_{code}_{index:03d}",
                    parent_path=field_path,
                    field_meta=field_meta,
                    param_meta=param_meta,
                )
                for index, item in enumerate(item_values, start=1)
            ]
        meta = _match_field_meta(field_meta or {}, str(code), field_path)
        param = _match_field_meta(param_meta or {}, str(code), field_path)
        field = _build_field(
            field_code=str(code),
            field_name=str(
                getattr(param, "param_name", "")
                or getattr(meta, "field_name", "")
                or getattr(meta, "property_name", "")
                or property_schema.get("description")
                or code
            ),
            field_type=field_type,
            field_value=field_value,
            children=children,
            field_path=field_path,
            required=str(code) in required,
            term=(
                _term_from_schema(property_schema)
                or _term_from_param(param)
                or _term_from_field_meta(meta)
            ),
        )
        if not fields:
            field["itemId"] = item_id
        fields.append(field)
    return fields


def _build_field_from_param(
    param: Any,
    tool_params: dict[str, Any],
    *,
    first: bool,
    form_id: str,
) -> dict[str, Any]:
    code = str(getattr(param, "param_code", "") or "")
    field = _build_field(
        field_code=code,
        field_name=str(getattr(param, "param_name", "") or code),
        field_type=_normalize_field_type(getattr(param, "param_type", "string")),
        field_value=tool_params.get(code, getattr(param, "default_value", None)),
        children=None,
        field_path=code,
        required=bool(getattr(param, "required", False)),
        term=_term_from_param(param),
    )
    if first:
        field["itemId"] = _build_item_id(form_id, 1)
    return field


def _build_field(
    *,
    field_code: str,
    field_name: str,
    field_type: str,
    field_value: Any,
    children: list[list[dict[str, Any]]] | None,
    field_path: str,
    required: bool,
    term: dict[str, Any] | None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "formType": _form_type(field_type, term),
        "fieldCode": field_code,
        "fieldPath": field_path,
        "fieldName": field_name,
        "fieldType": field_type,
        "required": required,
        "readonly": False,
        "disabled": False,
        "isHidden": False,
        "defaultFiles": [],
    }
    if children is not None:
        field["children"] = children
    else:
        field["fieldValue"] = field_value
    if term:
        field["term"] = term
    return field


def _schema_field_type(schema: dict[str, Any]) -> str:
    return _normalize_field_type(schema.get("type") or "string")


def _normalize_field_type(raw_type: Any) -> str:
    normalized = str(raw_type or "string").lower()
    type_map = {
        "str": "string",
        "string": "string",
        "integer": "integer",
        "int": "integer",
        "long": "integer",
        "number": "number",
        "decimal": "number",
        "double": "number",
        "float": "number",
        "boolean": "boolean",
        "bool": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
    }
    return type_map.get(normalized, "string")


def _form_type(field_type: str, term: dict[str, Any] | None) -> str:
    if term:
        return "term_select"
    return {
        "number": "number",
        "integer": "number",
        "boolean": "checkbox",
        "object": "object",
        "array": "array",
    }.get(field_type, "input")


def _term_from_param(param: Any) -> dict[str, Any] | None:
    term_set = str(getattr(param, "term_set", "") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code="",
        term_field=str(getattr(param, "term_field", "") or "").strip(),
        dataset_id=getattr(param, "dataset_id", None),
    )


def _term_from_field_meta(field: Any | None) -> dict[str, Any] | None:
    if field is None:
        return None
    term_set = str(getattr(field, "term_set", "") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code="",
        term_field=str(getattr(field, "term_field", "") or "").strip(),
        dataset_id=getattr(field, "dataset_id", None),
    )


def _term_from_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    term_raw = schema.get("term")
    if isinstance(term_raw, dict):
        term_set = str(term_raw.get("termSet") or term_raw.get("term_set") or "").strip()
        if term_set:
            return _build_term(
                term_set=term_set,
                term_type_code=str(
                    term_raw.get("termTypeCode") or term_raw.get("term_type_code") or ""
                ),
                term_field=str(term_raw.get("termField") or term_raw.get("term_field") or ""),
                dataset_id=term_raw.get("datasetId") or term_raw.get("dataset_id"),
            )
    term_set = str(schema.get("termSet") or schema.get("term_set") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code=str(schema.get("termTypeCode") or schema.get("term_type_code") or ""),
        term_field=str(schema.get("termField") or schema.get("term_field") or ""),
        dataset_id=schema.get("datasetId") or schema.get("dataset_id"),
    )


def _build_term(
    *,
    term_set: str,
    term_type_code: str,
    term_field: str,
    dataset_id: Any,
) -> dict[str, Any]:
    term: dict[str, Any] = {
        "termSet": term_set,
        "termTypeCode": term_type_code or term_set.split(".", 1)[0],
    }
    if term_field:
        term["termField"] = term_field
    if dataset_id is not None:
        term["datasetId"] = dataset_id
    return term


def _action_field_meta(action: Any) -> dict[str, Any]:
    scope = getattr(action, "_datacloud_scope", None)
    fields = getattr(scope, "fields", None)
    if not isinstance(fields, list):
        return {}
    result: dict[str, Any] = {}
    for field in fields:
        code = str(getattr(field, "field_code", "") or getattr(field, "property_code", "") or "")
        if code:
            result[code] = field
    return result


def _action_param_meta(action: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for param in list(getattr(action, "params", []) or []):
        code = str(getattr(param, "param_code", "") or "")
        if code:
            result[code] = param
        mapping_path = str(getattr(param, "mapping_path", "") or "")
        for key in _mapping_path_keys(mapping_path):
            result.setdefault(key, param)
    return result


def _mapping_path_keys(mapping_path: str) -> list[str]:
    if not mapping_path.startswith("$."):
        return []
    ignored_roots = {"requestBody", "body", "parameters", "query", "path", "headers", "header"}
    parts = [part[:-2] if part.endswith("[]") else part for part in mapping_path[2:].split(".")]
    return [part for part in parts if part and part != "[]" and part not in ignored_roots]


def _match_field_meta(field_meta: dict[str, Any], field_code: str, field_path: str) -> Any | None:
    if field_code in field_meta:
        return field_meta[field_code]
    leaf = field_path.split(".")[-1]
    return field_meta.get(leaf)


def _looks_like_2d_field_array(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, list) for row in value)
        and all(isinstance(item, dict) for row in value for item in row)
    )


def _parse_mapping_path(
    mapping_path: str,
    *,
    default_location: str,
) -> tuple[str, list[str]]:
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


def _normalize_mapping_location(location: str) -> str:
    return _MAPPING_LOCATION_ALIASES.get(location, location)


def _schema_location_key(location: str) -> str:
    return _LOCATION_SCHEMA_KEYS.get(_normalize_mapping_location(location), location)


def _ensure_object_schema(schema: dict[str, Any]) -> None:
    schema.setdefault("type", "object")
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        schema["properties"] = {}


def _ensure_array_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    schema.setdefault("type", "array")
    items = schema.setdefault("items", {"type": "object", "properties": {}})
    if not isinstance(items, dict):
        items = {"type": "object", "properties": {}}
        schema["items"] = items
    _ensure_object_schema(items)
    return items


def _append_required(schema: dict[str, Any], field_name: str) -> None:
    required = schema.setdefault("required", [])
    if isinstance(required, list) and field_name not in required:
        required.append(field_name)


def _assign_schema_path(
    root: dict[str, Any],
    path_parts: list[str],
    leaf_schema: dict[str, Any],
    *,
    required: bool,
) -> None:
    if not path_parts:
        _ensure_object_schema(root)
        properties = root.setdefault("properties", {})
        if isinstance(properties, dict):
            properties.update(leaf_schema)
        return

    current = root
    for index, raw_part in enumerate(path_parts):
        is_last = index == len(path_parts) - 1
        is_array = raw_part.endswith("[]")
        part = raw_part[:-2] if is_array else raw_part
        if not part:
            continue
        _ensure_object_schema(current)
        properties = current.setdefault("properties", {})
        if not isinstance(properties, dict):
            properties = {}
            current["properties"] = properties

        if is_last:
            properties[part] = {"type": "array", "items": leaf_schema} if is_array else leaf_schema
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
            current = _ensure_array_object_schema(node)
        else:
            node = properties.setdefault(part, {"type": "object", "properties": {}})
            if not isinstance(node, dict):
                node = {"type": "object", "properties": {}}
                properties[part] = node
            _ensure_object_schema(node)
            current = node


def _is_array_object_schema(schema: dict[str, Any]) -> bool:
    items = schema.get("items")
    return isinstance(items, dict) and str(items.get("type") or "").lower() == "object"


def _normalize_rule_rows(rule: list[Any]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for row in rule:
        if isinstance(row, list):
            fields = [dict(item) for item in row if isinstance(item, dict)]
            if fields:
                rows.append(fields)
    return rows


def _fields_to_object(
    fields: list[dict[str, Any]],
    *,
    use_field_path: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        field_code = str(field.get("fieldCode") or "").strip()
        if not field_code:
            continue
        field_path = str(field.get("fieldPath") or "").strip()
        result_key = field_path if use_field_path and field_path else field_code
        field_type = str(field.get("fieldType") or "").lower()
        value = field.get("fieldValue")
        children = field.get("children")
        if field_type == "object":
            nested_value = children if isinstance(children, list) else value
            rows = _normalize_rule_rows(nested_value if isinstance(nested_value, list) else [])
            value = _fields_to_object(rows[0]) if rows else {}
        elif field_type == "array" and (
            _looks_like_2d_field_array(children) or _looks_like_2d_field_array(value)
        ):
            nested_value = children if _looks_like_2d_field_array(children) else value
            rows = _normalize_rule_rows(nested_value if isinstance(nested_value, list) else [])
            value = [_fields_to_object(row) for row in rows]
        result[result_key] = value
    return result


def _set_path_value(target: dict[str, Any], field_path: str, value: Any) -> None:
    parts = [part for part in field_path.split(".") if part]
    if not parts:
        return
    cursor = target
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def _filter_restored_params(params: dict[str, Any], action: Any | None) -> dict[str, Any]:
    if action is None:
        return params
    schema = _get_action_input_schema(action)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return params
    allowed = set(properties) | {_CONFIRM_PARAM, _OPERATION_CONFIRM_PARAM}
    return {key: value for key, value in params.items() if key in allowed}


def _build_form_id(action: Any, params: dict[str, Any]) -> str:
    action_code = str(getattr(action, "action_code", "") or "operation")
    digest = _stable_hash({"actionCode": action_code, "params": params})[:16]
    return f"op_form_{digest}"


def _build_item_id(form_id: str, index: int) -> str:
    return f"{form_id}_item_{index:03d}"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
