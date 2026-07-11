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


def _normalize_entity(
    entity_type: str, data: dict[str, Any], *, for_storage: bool = False
) -> dict[str, Any]:
    """Normalize an entity dict from model_dump(by_alias=True) camelCase to canonical format.

    Handles both write-side (for_storage=True — canonicalize before EntityStore.save)
    and read-side (for_storage=False — normalize legacy data for read paths).

    The canonical format uses snake_case keys that match what OntologyLoader and
    _raw_to_*_dict read paths expect.  All field-level normalization (ObjectType
    properties → fields, ViewProperty → mappings, ActionParam isRequired → required)
    is handled here so downstream code never sees camelCase keys.
    """
    result = dict(data)

    if entity_type == "object":
        result.setdefault("object_code", data.get("objectCode", ""))
        result.setdefault("object_name", data.get("objectName", ""))
        result.setdefault(
            "source_type",
            data.get("source_type")
            or data.get("sourceType")
            or data.get("objectSource", "DB"),
        )
        result.setdefault(
            "description", data.get("description") or data.get("objectDesc", "")
        )
        result.setdefault(
            "concept_type", data.get("concept_type") or data.get("conceptType")
        )
        result.setdefault(
            "datasource_alias",
            data.get("datasource_alias") or data.get("datasourceAlias"),
        )
        result.setdefault("table_name", data.get("table_name") or data.get("tableName"))
        result.setdefault(
            "source_config", data.get("source_config") or data.get("sourceConfig")
        )
        # DYNAMIC_TABLE objects need a datasource_alias and table_name for the executor.
        # Legacy objects created before these were required get a default.
        if str(result.get("source_type", "")).upper() == "DYNAMIC_TABLE":
            result.setdefault("datasource_alias", _DEFAULT_DYNAMIC_DATASOURCE_ALIAS)
            result.setdefault("table_name", result.get("object_code", ""))
            # setdefault won't override an existing key (including None), so
            # explicitly set if the value is still falsy after setdefault.
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
        result.setdefault(
            "ext_property", data.get("ext_property") or data.get("extProperty", {})
        )
        result.setdefault("tags", data.get("tags", []))
        # properties → fields with field-level normalization
        raw_props = data.get("properties") or data.get("fields", [])
        if raw_props and not data.get("fields"):
            result["fields"] = [
                {
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
                }
                for p in raw_props
            ]
        # actions: forward as-is (model_dump key names happen to match)
        result.setdefault("actions", data.get("actions", []))

    elif entity_type == "view":
        result.setdefault(
            "view_code",
            data.get("view_code")
            or data.get("viewCode")
            or data.get("view_id")
            or data.get("viewId", ""),
        )
        result.setdefault(
            "view_name", data.get("view_name") or data.get("viewName", "")
        )
        result.setdefault(
            "description", data.get("description") or data.get("viewDesc")
        )
        # objectCodes → objects
        raw_codes = data.get("objects") or data.get("objectCodes") or []
        if raw_codes and not data.get("objects"):
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
        result.setdefault(
            "owner_type", data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result.setdefault("user_code", data.get("user_code") or data.get("userCode"))

    elif entity_type == "relation":
        result.setdefault(
            "relation_code",
            data.get("relation_code") or data.get("relationCode", ""),
        )
        result.setdefault(
            "relation_name",
            data.get("relation_name") or data.get("relationName"),
        )
        result.setdefault(
            "relation_cardinality",
            data.get("relation_cardinality")
            or data.get("relationCardinality")
            or data.get("relation_type"),
        )
        result.setdefault(
            "relation_desc",
            data.get("relation_desc")
            or data.get("description")
            or data.get("relationDesc"),
        )
        result.setdefault(
            "relation_scene_type",
            data.get("relation_scene_type") or data.get("relationSceneType"),
        )
        # sourceObjectCode / targetObjectCode → source_class / target_class
        result.setdefault(
            "source_class",
            data.get("source_class") or data.get("sourceObjectCode", ""),
        )
        result.setdefault(
            "target_class",
            data.get("target_class") or data.get("targetObjectCode", ""),
        )
        result.setdefault(
            "owner_type",
            str(data.get("owner_type") or data.get("ownerType", "enterprise")),
        )
        result.setdefault("user_code", data.get("user_code") or data.get("userCode"))

    elif entity_type == "action":
        result.setdefault(
            "action_code", data.get("action_code") or data.get("actionCode", "")
        )
        result.setdefault(
            "action_name", data.get("action_name") or data.get("actionName", "")
        )
        result.setdefault(
            "action_type", data.get("action_type") or data.get("actionType")
        )
        result.setdefault(
            "belong_object_code",
            data.get("belong_object_code") or data.get("belongObjectCode", ""),
        )
        result.setdefault(
            "action_desc",
            data.get("action_desc")
            or data.get("description")
            or data.get("actionDesc"),
        )
        result.setdefault(
            "request_url", data.get("request_url") or data.get("requestUrl")
        )
        result.setdefault(
            "request_method", data.get("request_method") or data.get("requestMethod")
        )
        result.setdefault(
            "owner_type", data.get("owner_type") or data.get("ownerType", "enterprise")
        )
        result.setdefault("user_code", data.get("user_code") or data.get("userCode"))
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
        pass

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
