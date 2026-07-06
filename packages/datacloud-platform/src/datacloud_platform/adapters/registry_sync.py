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
    """Convert a camelCase Action dict to OWL snake_case for objects_registry.json."""
    params: list[dict[str, Any]] = [
        {
            "param_code": p.get("paramCode", ""),
            "param_name": p.get("paramName") or p.get("paramCode", ""),
            "param_type": p.get("paramType") or "STRING",
            "required": bool(p.get("isRequired", 0)),
            "direction": p.get("direction") or "IN",
            "mapping_path": p.get("mappingPath") or p.get("mapping_path", ""),
            "data_format": p.get("dataFormat") or p.get("data_format"),
            "default_value": p.get("defaultValue") or p.get("default_value"),
            "json_path": p.get("jsonPath") or p.get("json_path", ""),
            "object_property": p.get("objectProperty") or p.get("object_property"),
            "object_code": p.get("objectCode") or p.get("object_code"),
        }
        for p in a.get("params", [])
        if p.get("paramCode") or p.get("param_code")
    ]
    result: dict[str, Any] = {
        "action_code": a.get("actionCode") or a.get("action_code", ""),
        "action_name": a.get("actionName") or a.get("action_name") or a.get("actionCode", ""),
        "action_type": a.get("actionType") or a.get("action_type") or "",
        "description": a.get("actionDesc") or a.get("description", ""),
        "belong_class": a.get("belongObjectCode") or a.get("belong_class", ""),
        "params": params,
        "script": a.get("script"),
        "request_url": a.get("requestUrl") or a.get("request_url"),
        "request_method": a.get("requestMethod") or a.get("request_method"),
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
    """Convert a camelCase ObjectType dict to OWL snake_case for objects_registry.json.

    Preserves actions (with script/params/object_references), term_sync, and
    ext_property (promoted from sourceConfig when absent) so that
    OntologyLoader.load_from_content can correctly restore runtime behaviour.
    """
    fields: list[dict[str, Any]] = []
    for p in obj_dict.get("properties", []):
        field_entry: dict[str, Any] = {
            "field_code": p.get("propertyCode", ""),
            "field_name": p.get("propertyName", ""),
            "field_type": p.get("dataType", "STRING"),
            "description": p.get("propertyDesc") or p.get("description", ""),
            "required": bool(p.get("isRequired", 0)),
            "data_format": p.get("dataFormat") or p.get("data_format"),
            "is_primary_key": p.get("businessKey", 0) == 1,
            "source_column": p.get("sourceColumn") or p.get("source_column"),
        }
        # Carry termMeta so loader can restore term_type / term_set
        term_meta = p.get("terminology")
        if term_meta and isinstance(term_meta, dict):
            field_entry["termMeta"] = term_meta
        fields.append(field_entry)

    result: dict[str, Any] = {
        "object_code": obj_dict.get("objectCode", ""),
        "object_name": obj_dict.get("objectName", ""),
        "description": obj_dict.get("objectDesc") or "",
        "source_type": obj_dict.get("objectSource") or "",
        "concept_type": obj_dict.get("conceptType") or "",
        "table_name": obj_dict.get("tableName") or "",
        "fields": fields,
        "actions": [
            _action_camel_to_owl(a)
            for a in obj_dict.get("actions", [])
            if a.get("actionCode") or a.get("action_code")
        ],
    }
    # Write source_config so loader can extract datasource_alias for DB objects
    source_config = obj_dict.get("source_config") or obj_dict.get("sourceConfig")
    if isinstance(source_config, dict):
        result["source_config"] = source_config
    # Promote kb_id/kb_directory from sourceConfig into ext_property
    ext_property: dict[str, Any] = dict(
        obj_dict.get("ext_property") or obj_dict.get("extProperty") or {}
    )
    source_config = obj_dict.get("source_config") or obj_dict.get("sourceConfig")
    if isinstance(source_config, dict):
        for kb_key in ("kb_id", "kb_directory", "knCode"):
            if source_config.get(kb_key) and kb_key not in ext_property:
                ext_property[kb_key] = source_config[kb_key]
    if ext_property:
        result["ext_property"] = ext_property
    # Carry term_sync (stored as extra field in ObjectType.model_extra)
    term_sync = obj_dict.get("term_sync")
    if term_sync:
        result["term_sync"] = term_sync
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
        "relation_code": rel_dict.get("relationCode") or rel_dict.get("relation_code", ""),
        "relation_name": rel_dict.get("relationName") or rel_dict.get("relation_name", ""),
        "source_class": rel_dict.get("sourceObjectCode") or rel_dict.get("source_class", ""),
        "target_class": rel_dict.get("targetObjectCode") or rel_dict.get("target_class", ""),
        "relation_type": relation_type,
        "join_keys": join_keys,
        "description": rel_dict.get("relationDesc") or rel_dict.get("description", ""),
    }


def view_camel_to_registry(view_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert a camelCase View dict to registry snake_case for objects_registry.json."""
    return {
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
