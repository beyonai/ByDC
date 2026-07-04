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


def obj_camel_to_owl(obj_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert a camelCase ObjectType dict to OWL snake_case for objects_registry.json."""
    return {
        "object_code": obj_dict.get("objectCode", ""),
        "object_name": obj_dict.get("objectName", ""),
        "description": obj_dict.get("objectDesc") or "",
        "source_type": obj_dict.get("objectSource") or "",
        "concept_type": obj_dict.get("conceptType") or "",
        "table_name": obj_dict.get("tableName") or "",
        "fields": [
            {
                "field_code": p.get("propertyCode", ""),
                "field_name": p.get("propertyName", ""),
                "field_type": p.get("dataType", "STRING"),
                "is_primary_key": p.get("businessKey", 0) == 1,
                "source_column": p.get("sourceColumn"),
            }
            for p in obj_dict.get("properties", [])
        ],
        "actions": [],
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
