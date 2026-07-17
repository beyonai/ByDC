"""Base mixin — __init__, entity_store, knowledge SDK lazy init, static helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.models import ObjectSummary, ViewSummary
from datacloud_platform.ports.entity_store import EntityStore

logger = logging.getLogger(__name__)


_STORAGE_DIR_ENV = "DATACLOUD_STORAGE_DIR"
_DEFAULT_STORAGE_DIR = ".datacloud_results"

# Default datasource alias for DYNAMIC_TABLE objects created without OWL.
# Must match the alias registered by _ensure_default_datasource in _ontology.py.
_DEFAULT_DYNAMIC_DATASOURCE_ALIAS = "__dynamic_table__"


def _normalize_object_codes(raw_objects: list[Any]) -> list[str]:
    """Normalize view ``objects`` entries into a flat list of object codes.

    Each entry may be a plain ``str`` or a ``dict`` with an ``object_code`` key.
    """
    codes: list[str] = []
    for item in raw_objects:
        if isinstance(item, str):
            codes.append(item)
        elif isinstance(item, dict):
            code = item.get("object_code", "")
            if code:
                codes.append(code)
    return codes


def _normalize_terminology(
    raw: Any,
) -> tuple[dict[str, Any], str | None, str | None, str | None]:
    """Normalize terminology/termMeta to (terminology, term_set, term_type, term_field)."""
    if not raw:
        return {}, None, None, None
    if not isinstance(raw, dict):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(by_alias=True)
        else:
            return {}, None, None, None

    term_type_code = raw.get("termTypeCode") or raw.get("term_type_code")
    term_field = raw.get("termField") or raw.get("term_field")
    term_master_type = str(
        raw.get("termMasterType") or raw.get("term_master_type") or ""
    ).lower()

    term_set = f"{term_type_code}.code" if term_type_code and term_field else None
    term_type = None
    if term_master_type in ("dict", "dict_term"):
        term_type = "enum"
    elif term_master_type in ("list", "list_term", "ontology", "ontology_term"):
        term_type = "lookup"

    return raw, term_set, term_type, term_field


def _normalize_property_field(p: dict[str, Any]) -> dict[str, Any]:
    """Normalize ObjectType property dict to SDK field dict."""
    terminology, term_set, term_type, term_field = _normalize_terminology(
        p.get("terminology") or p.get("termMeta") or p.get("term_meta")
    )
    return {
        "field_code": p.get("field_code") or p.get("propertyCode", ""),
        "field_name": p.get("field_name") or p.get("propertyName", ""),
        "field_type": p.get("field_type") or p.get("dataType", "STRING"),
        "data_format": p.get("data_format") or p.get("dataFormat"),
        "description": p.get("description") or p.get("propertyDesc", ""),
        "is_primary_key": (
            bool(p.get("is_primary_key")) or p.get("businessKey", 0) == 1
        ),
        "required": bool(p.get("required") or p.get("isRequired", False)),
        "source_column": p.get("source_column") or p.get("sourceColumn"),
        "terminology": terminology,
        "term_set": p.get("term_set") or term_set,
        "term_type": p.get("term_type") or term_type,
        "term_field": p.get("term_field") or term_field,
    }


def _normalize_entity(
    entity_type: str, data: dict[str, Any], *, for_storage: bool = False
) -> dict[str, Any]:
    """Normalize an entity dict from model_dump(by_alias=True) camelCase to canonical format.

    Produces ONLY canonical snake_case keys — no camelCase residual.
    All field-level normalization (ObjectType properties → fields, ViewProperty → mappings,
    ActionParam isRequired → required) is handled here.
    """
    result: dict[str, Any] = {}

    if entity_type == "object":
        result["object_code"] = data.get("object_code") or data.get("objectCode", "")
        result["object_name"] = data.get("object_name") or data.get("objectName", "")
        result["source_type"] = (
            data.get("source_type")
            or data.get("sourceType")
            or data.get("objectSource", "DB")
        )
        result["description"] = data.get("description") or data.get("objectDesc", "")
        result["concept_type"] = data.get("concept_type") or data.get("conceptType")
        result["datasource_alias"] = data.get("datasource_alias") or data.get(
            "datasourceAlias"
        )
        result["table_name"] = data.get("table_name") or data.get("tableName")
        result["source_config"] = data.get("source_config") or data.get("sourceConfig")
        result["ext_property"] = (
            data.get("ext_property") or data.get("extProperty") or {}
        )
        result["tags"] = data.get("tags") or []
        result["owner_type"] = str(
            data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result["user_code"] = data.get("user_code") or data.get("userCode")

        result["term_sync"] = data.get("term_sync") or data.get("termSync")

        # DYNAMIC_TABLE objects need a datasource_alias and table_name for the executor.
        if str(result.get("source_type", "")).upper() == "DYNAMIC_TABLE":
            if not result.get("datasource_alias"):
                result["datasource_alias"] = _DEFAULT_DYNAMIC_DATASOURCE_ALIAS
            if not result.get("table_name"):
                result["table_name"] = result.get("object_code", "")
            sc = result.get("source_config")
            if not isinstance(sc, dict):
                sc = {}
                result["source_config"] = sc
            if not sc.get("alias"):
                sc["alias"] = _DEFAULT_DYNAMIC_DATASOURCE_ALIAS
            if not sc.get("jdbc_url"):
                mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
                if mount:
                    sc["jdbc_url"] = (
                        f"jdbc:sqlite:{mount}/byclaw-datacloud/personal_object.db"
                    )

        # properties → fields with field-level normalization
        raw_props = data.get("properties") or data.get("fields", [])
        if raw_props and not data.get("fields"):
            result["fields"] = [_normalize_property_field(p) for p in raw_props]
        elif data.get("fields"):
            result["fields"] = data["fields"]
        result["actions"] = data.get("actions") or []

    elif entity_type == "view":
        result["view_code"] = (
            data.get("view_code")
            or data.get("viewCode")
            or data.get("view_id")
            or data.get("viewId", "")
        )
        result["view_name"] = data.get("view_name") or data.get("viewName", "")
        result["description"] = data.get("description") or data.get("viewDesc")

        # objectCodes → objects
        raw_codes = data.get("objects") or data.get("objectCodes") or []
        result["objects"] = raw_codes

        # properties → mappings with ViewProperty → mapping normalization
        raw_view_props = data.get("mappings") or data.get("properties", [])
        if raw_view_props and not data.get("mappings"):
            result["mappings"] = [
                {
                    "property_name": m.get("property_name")
                    or m.get("propertyName", ""),
                    "property_code": m.get("property_code")
                    or m.get("propertyCode", ""),
                    "source_object_code": m.get("source_object_code")
                    or m.get("sourceObject", ""),
                    "source_object_column_code": m.get("source_object_column_code")
                    or m.get("sourceObjectProperty", ""),
                }
                for m in raw_view_props
            ]
        elif data.get("mappings"):
            result["mappings"] = data["mappings"]

        result["owner_type"] = str(
            data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result["user_code"] = data.get("user_code") or data.get("userCode")

    elif entity_type == "relation":
        result["relation_code"] = data.get("relation_code") or data.get(
            "relationCode", ""
        )
        result["relation_name"] = data.get("relation_name") or data.get(
            "relationName", ""
        )
        result["relation_type"] = (
            data.get("relation_type")
            or data.get("relation_cardinality")
            or data.get("relationCardinality", "MANY_TO_ONE")
        )
        result["description"] = (
            data.get("description")
            or data.get("relation_desc")
            or data.get("relationDesc", "")
        )
        result["relation_scene_type"] = data.get("relation_scene_type") or data.get(
            "relationSceneType"
        )
        result["source_class"] = data.get("source_class") or data.get(
            "sourceObjectCode", ""
        )
        result["target_class"] = data.get("target_class") or data.get(
            "targetObjectCode", ""
        )
        result["owner_type"] = str(
            data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result["user_code"] = data.get("user_code") or data.get("userCode")

        # Extract join_keys from attribute JSON to top-level
        attr = data.get("attribute")
        if isinstance(attr, dict):
            jk = attr.get("join_keys") or attr.get("joinKeys")
            if jk:
                result["join_keys"] = jk
        # Also preserve top-level join_keys (OWL / direct format)
        if "join_keys" not in result:
            top_jk = data.get("join_keys") or data.get("joinKeys")
            if top_jk:
                result["join_keys"] = top_jk

    elif entity_type == "action":
        result["action_code"] = data.get("action_code") or data.get("actionCode", "")
        result["action_name"] = data.get("action_name") or data.get("actionName", "")
        result["action_type"] = data.get("action_type") or data.get("actionType")
        result["belong_object_code"] = data.get("belong_object_code") or data.get(
            "belongObjectCode", ""
        )
        result["description"] = (
            data.get("description")
            or data.get("action_desc")
            or data.get("actionDesc", "")
        )
        result["request_url"] = data.get("request_url") or data.get("requestUrl")
        result["request_method"] = data.get("request_method") or data.get(
            "requestMethod"
        )
        result["owner_type"] = str(
            data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result["user_code"] = data.get("user_code") or data.get("userCode")

        # Normalize params: isRequired → required
        raw_params = data.get("params", [])
        if raw_params:
            result["params"] = [
                {
                    **p,
                    "required": bool(p.get("required") or p.get("isRequired", False)),
                }
                for p in raw_params
            ]

    elif entity_type == "datasource":
        # Datasource model_dump keys (dbId, dbCode, dbType, dbParams) match read path expectations
        result = dict(data)

    return result


def _build_sync_payload(
    resource_type: str,
    resource_code: str,
    resource_name: str,
    resource_desc: str = "",
    base_code: str = "",
    owner_type: str = "enterprise",
) -> dict[str, Any]:
    """Build a standardized sync payload for ByClaw resource table."""
    from datacloud_platform.constants import DEFAULT_SYSTEM_CODE

    return {
        "systemCode": DEFAULT_SYSTEM_CODE,
        "resourceBizType": resource_type,
        "resourceCode": resource_code,
        "resourceName": resource_name,
        "resourceDesc": resource_desc,
        "ontologyBaseCode": base_code,
        "ownerType": owner_type,
    }


class DataCloudDataBackendBase:
    """Foundation mixin: __init__, entity_store, knowledge SDK lazy init, static helpers."""

    def __init__(self, entity_store: EntityStore | None = None) -> None:
        if entity_store is None:
            from datacloud_platform.platform_file_storage import _data_dir

            entity_store = JsonEntityStore(_data_dir())
        self._entity_store: EntityStore = entity_store
        self._scenes: dict[str, dict[str, Any]] | None = None
        self._scenes_version: str = ""
        self._object_scene_map: dict[str, set[str]] = {}
        self._view_scene_map: dict[str, set[str]] = {}
        self._reverse_index_built: bool = False

        # Lazy knowledge SDK objects (initialised on first use)
        self._knowledge_reader: Any = None
        self._knowledge_search_engine: Any = None
        self._knowledge_embedding: Any = None

    # ── Knowledge SDK lazy init helpers ────────────────────────────────────

    def _get_knowledge_reader(self) -> Any:
        if self._knowledge_reader is None:
            from datacloud_knowledge.adapters import create_reader  # noqa: PLC0415

            self._knowledge_reader = create_reader()
        return self._knowledge_reader

    def _get_search_engine(self) -> Any:
        if self._knowledge_search_engine is None:
            from datacloud_knowledge.adapters.opengauss.engine import (  # noqa: PLC0415
                PostgresSearchEngine,
            )

            self._knowledge_search_engine = PostgresSearchEngine()
        return self._knowledge_search_engine

    def _get_embedding(self) -> Any:
        if self._knowledge_embedding is None:
            from datacloud_knowledge.retrieval.embedding.service import (  # noqa: PLC0415
                EmbeddingService,
            )

            self._knowledge_embedding = EmbeddingService()
        return self._knowledge_embedding

    # ── internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_base_path(base_id: str) -> Path:
        """Resolve a base_id to a filesystem path, honouring backend_config.ontology.base_path."""
        try:
            from datacloud_platform import get_platform

            platform = get_platform()
            if hasattr(platform, "_base_path_for"):
                return platform._base_path_for(base_id)
        except Exception:  # noqa: BLE001
            pass
        from datacloud_platform.platform_file_storage import _data_dir

        return _data_dir() / base_id

    @staticmethod
    def _to_summary(ont_class: object) -> ObjectSummary:
        """Convert an OntologyClass-like object to ObjectSummary."""
        object_code: str = getattr(ont_class, "object_code", "")
        object_name: str = getattr(ont_class, "object_name", "")
        description: str = getattr(ont_class, "description", "")
        source_type: str = getattr(ont_class, "source_type", "")
        field_count: int = len(getattr(ont_class, "fields", []))
        action_count: int = len(getattr(ont_class, "actions", []))
        owner_type: str = (getattr(ont_class, "ext_property", None) or {}).get(
            "owner_type", "enterprise"
        )
        user_code: str | None = (getattr(ont_class, "ext_property", None) or {}).get(
            "user_code"
        )
        return ObjectSummary(
            object_code=object_code,
            object_name=object_name,
            description=description,
            object_source=source_type,
            field_count=field_count,
            action_count=action_count,
            owner_type=owner_type,
            user_code=user_code,
        )

    @staticmethod
    def _to_view_summary(view_data: dict[str, Any], view_code: str) -> ViewSummary:
        """Convert a raw view dict to ViewSummary."""
        normalized_codes = _normalize_object_codes(view_data.get("objects", []))
        ext = view_data.get("ext_property", {}) or {}
        owner_type: str = ext.get(
            "owner_type",
            view_data.get("owner_type", view_data.get("ownerType", "enterprise")),
        )
        user_code: str | None = ext.get(
            "user_code", view_data.get("user_code", view_data.get("userCode"))
        )
        return ViewSummary(
            view_code=view_data.get("view_id", view_code),
            view_name=view_data.get("view_name", ""),
            description=view_data.get("description", "") or "",
            object_codes=normalized_codes,
            owner_type=owner_type,
            user_code=user_code,
        )

    @staticmethod
    def _storage_dir() -> Path:
        """Resolve storage directory from env or default."""
        env_dir = os.getenv(_STORAGE_DIR_ENV)
        if env_dir:
            return Path(env_dir)
        return Path(_DEFAULT_STORAGE_DIR)

    def _invoke_sync_hook(self, method: str, resource_type: str, **kwargs: Any) -> None:
        """Invoke sync hook if configured. Never raises."""
        hook = getattr(self, "_sync_hook", None)
        if hook is None:
            logger.warning(
                "Sync hook not configured — skipping %s(%s)",
                method,
                resource_type,
            )
            return
        try:
            if method in ("on_create", "on_update"):
                payload = _build_sync_payload(resource_type, **kwargs)
                if method == "on_create":
                    hook.on_create(resource_type, payload)
                else:
                    hook.on_update(resource_type, payload)
            elif method == "on_delete":
                hook.on_delete(resource_type, **kwargs)
        except Exception:
            logger.warning(
                "Sync hook failed: method=%s type=%s",
                method,
                resource_type,
                exc_info=True,
            )
