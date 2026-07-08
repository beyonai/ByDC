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
