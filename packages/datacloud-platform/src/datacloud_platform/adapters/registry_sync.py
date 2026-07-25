"""Registry sync helpers — keep objects_registry.json consistent with CRUD operations.

Used by platform-layer mixins (scene_service, ontology_crud) which have access to
the correct base_path via _base_path_for(base_id), bypassing the adapter-level
_resolve_base_path that always appends base_id and may diverge from the configured path.
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import Any

from datacloud_platform.platform_file_storage import atomic_write_json

logger = logging.getLogger(__name__)


def _action_camel_to_owl(a: dict[str, Any]) -> dict[str, Any]:
    """Convert an Action dict to loader-native snake_case format."""
    params: list[dict[str, Any]] = []
    for p in a.get("params", []):
        param_code = p.get("param_code") or p.get("paramCode", "")
        if not param_code:
            continue
        param_entry: dict[str, Any] = {
            "param_code": param_code,
            "param_name": p.get("param_name") or p.get("paramName") or param_code,
            "param_type": p.get("param_type") or p.get("paramType") or "STRING",
            "required": bool(p.get("required") or p.get("isRequired", 0)),
            "direction": p.get("direction") or "IN",
            "mapping_path": p.get("mapping_path") or p.get("mappingPath", ""),
            "data_format": p.get("data_format") or p.get("dataFormat"),
            "default_value": p.get("default_value") or p.get("defaultValue"),
            "json_path": p.get("json_path") or p.get("jsonPath", ""),
            "object_property": p.get("object_property") or p.get("objectProperty"),
            "object_code": p.get("object_code") or p.get("objectCode"),
        }
        term_meta = p.get("termMeta") or p.get("term_meta")
        if isinstance(term_meta, dict):
            param_entry["termMeta"] = term_meta
        if p.get("term_values"):
            param_entry["term_values"] = p["term_values"]
        if p.get("term_set"):
            param_entry["term_set"] = p["term_set"]
        params.append(param_entry)

    result: dict[str, Any] = {
        "action_code": a.get("action_code") or a.get("actionCode", ""),
        "action_name": a.get("action_name")
        or a.get("actionName")
        or a.get("action_code")
        or a.get("actionCode", ""),
        "action_type": a.get("action_type") or a.get("actionType") or "",
        "description": a.get("description") or a.get("actionDesc", ""),
        "belong_class": a.get("belong_class") or a.get("belongObjectCode", ""),
        "params": params,
        "script": a.get("script"),
        "request_url": a.get("request_url") or a.get("requestUrl"),
        "request_method": a.get("request_method") or a.get("requestMethod"),
    }
    # carry through object_references and function_refs if present
    obj_refs = a.get("object_references") or a.get("objectReferences")
    if obj_refs:
        result["object_references"] = obj_refs
    fn_refs = a.get("function_refs") or a.get("functionRefs")
    if fn_refs:
        result["function_refs"] = fn_refs
    return result


def obj_camel_to_owl(obj_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert ObjectType/API dict to loader-native snake_case format.

    The returned payload is what OntologyLoader.load_from_content() consumes:
    object_code/object_name/source_type/fields/actions/source_config/ext_property.
    Both API camelCase and loader snake_case inputs are supported.
    """
    raw_fields = obj_dict.get("fields") or obj_dict.get("properties", [])
    fields: list[dict[str, Any]] = []
    for p in raw_fields:
        field_code = p.get("field_code") or p.get("propertyCode", "")
        if not field_code:
            continue
        field_entry: dict[str, Any] = {
            "field_code": field_code,
            "field_name": p.get("field_name") or p.get("propertyName") or field_code,
            "field_type": p.get("field_type") or p.get("dataType", "STRING"),
            "description": p.get("description") or p.get("propertyDesc", ""),
            "required": bool(p.get("required") or p.get("isRequired", 0)),
            "data_format": p.get("data_format") or p.get("dataFormat"),
            "is_primary_key": bool(p.get("is_primary_key"))
            or p.get("businessKey", 0) == 1,
            "source_column": p.get("source_column") or p.get("sourceColumn"),
        }
        term_meta = p.get("termMeta") or p.get("term_meta") or p.get("terminology")
        if isinstance(term_meta, dict):
            field_entry["termMeta"] = term_meta
        if p.get("term_set"):
            field_entry["term_set"] = p["term_set"]
        if p.get("term_values"):
            field_entry["term_values"] = p["term_values"]
        field_ext_property = p.get("ext_property") or p.get("extProperty")
        if isinstance(field_ext_property, dict):
            field_entry["ext_property"] = field_ext_property
        for extra_key in (
            "aliases",
            "physical_mappings",
            "property_kind",
            "derived_config",
            "relation_ref",
            "resolve_action_code",
            "resolve_param_binding",
        ):
            if extra_key in p:
                field_entry[extra_key] = p[extra_key]
        fields.append(field_entry)

    result: dict[str, Any] = {
        "object_code": obj_dict.get("object_code") or obj_dict.get("objectCode", ""),
        "object_name": obj_dict.get("object_name") or obj_dict.get("objectName", ""),
        "description": obj_dict.get("description") or obj_dict.get("objectDesc", ""),
        "source_type": obj_dict.get("source_type")
        or obj_dict.get("objectSource")
        or "DB",
        "concept_type": obj_dict.get("concept_type")
        or obj_dict.get("conceptType")
        or "",
        "table_name": obj_dict.get("table_name") or obj_dict.get("tableName") or "",
        "fields": fields,
        "actions": [
            _action_camel_to_owl(a)
            for a in obj_dict.get("actions", [])
            if a.get("action_code") or a.get("actionCode")
        ],
    }
    source_config = obj_dict.get("source_config") or obj_dict.get("sourceConfig")
    if isinstance(source_config, dict):
        result["source_config"] = source_config
    datasource_alias = obj_dict.get("datasource_alias") or obj_dict.get(
        "datasourceAlias"
    )
    if datasource_alias:
        result["datasource_alias"] = datasource_alias

    ext_property: dict[str, Any] = dict(
        obj_dict.get("ext_property") or obj_dict.get("extProperty") or {}
    )
    _owner = obj_dict.get("owner_type") or obj_dict.get("ownerType")
    if _owner and _owner != "enterprise":
        result["owner_type"] = _owner
        ext_property.setdefault("owner_type", _owner)
    _user = obj_dict.get("user_code") or obj_dict.get("userCode")
    if _user:
        result["user_code"] = _user
        ext_property.setdefault("user_code", _user)
    if isinstance(source_config, dict):
        for kb_key in ("kb_id", "kb_directory", "knCode"):
            if source_config.get(kb_key) and kb_key not in ext_property:
                ext_property[kb_key] = source_config[kb_key]
    if ext_property:
        result["ext_property"] = ext_property

    term_sync = obj_dict.get("term_sync") or obj_dict.get("termSync")
    if term_sync:
        result["term_sync"] = term_sync
    tags = obj_dict.get("tags")
    if tags:
        result["tags"] = tags
    return result


def rel_camel_to_registry(rel_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert a camelCase Relation dict to OWL snake_case for objects_registry.json."""
    # join_keys: stored in attribute.joinKeys or attribute.join_keys
    attribute = rel_dict.get("attribute") or {}
    join_keys: list[dict[str, str]] = (
        attribute.get("joinKeys") or attribute.get("join_keys") or []
    )
    relation_type: str = (
        attribute.get("relationType")
        or attribute.get("relation_type")
        or rel_dict.get("relationCardinality")
        or rel_dict.get("relation_cardinality")
        or "ONE_TO_MANY"
    )
    return {
        "relation_code": rel_dict.get("relationCode")
        or rel_dict.get("relation_code", ""),
        "relation_name": rel_dict.get("relationName")
        or rel_dict.get("relation_name", ""),
        "source_class": rel_dict.get("sourceObjectCode")
        or rel_dict.get("source_class", ""),
        "target_class": rel_dict.get("targetObjectCode")
        or rel_dict.get("target_class", ""),
        "relation_type": relation_type,
        "join_keys": join_keys,
        "description": rel_dict.get("relationDesc") or rel_dict.get("description", ""),
    }


def view_camel_to_registry(view_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert a camelCase View dict to registry snake_case for objects_registry.json."""
    result: dict[str, Any] = {
        "view_id": view_dict.get("viewCode", ""),
        "view_name": view_dict.get("viewName", ""),
        "description": view_dict.get("description") or "",
        "objects": view_dict.get("objectCodes", []),
        "mappings": [
            {
                "property_name": p.get("propertyName", ""),
                "property_code": p.get("propertyCode", ""),
                "source_object_code": p.get("sourceObject", ""),
                "source_object_column_code": p.get("sourceObjectProperty", ""),
            }
            for p in view_dict.get("properties", [])
        ],
    }
    # Persist owner_type/user_code in ext_property (extension bag)
    ext_property: dict[str, Any] = {}
    _owner = view_dict.get("ownerType")
    if _owner and _owner != "enterprise":
        ext_property["owner_type"] = _owner
    _user = view_dict.get("userCode")
    if _user:
        ext_property["user_code"] = _user
    if ext_property:
        result["ext_property"] = ext_property
    return result


def registry_sync_upsert(
    base_path: Path, list_key: str, code_key: str, code: str, entry: dict[str, Any]
) -> None:
    """Read objects_registry.json, upsert one entry under list_key, write back atomically."""
    registry_path = base_path / "objects_registry.json"
    try:
        content: dict[str, Any] = _json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        content = {"objects": [], "views": [], "relations": []}
    items: list[dict[str, Any]] = content.setdefault(list_key, [])
    idx = next((i for i, o in enumerate(items) if o.get(code_key) == code), -1)
    if idx >= 0:
        items[idx] = entry
    else:
        items.append(entry)
    atomic_write_json(registry_path, content)
    logger.debug(
        "registry_sync_upsert: %s %s=%s → %s", list_key, code_key, code, registry_path
    )


def registry_sync_delete(
    base_path: Path, list_key: str, code_key: str, code: str
) -> None:
    """Read objects_registry.json, remove one entry under list_key, write back atomically."""
    registry_path = base_path / "objects_registry.json"
    try:
        content: dict[str, Any] = _json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    items: list[dict[str, Any]] = content.get(list_key, [])
    content[list_key] = [o for o in items if o.get(code_key) != code]
    atomic_write_json(registry_path, content)
    logger.debug(
        "registry_sync_delete: %s %s=%s → %s", list_key, code_key, code, registry_path
    )
