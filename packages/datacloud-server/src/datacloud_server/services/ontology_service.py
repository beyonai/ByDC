"""OntologyService - service layer orchestration + adapter routing.

Thin orchestration: DI (Registry + Repository), routing + permission check.
"""

from __future__ import annotations

import logging
from typing import Protocol

from datacloud_server.registry.registry import OntologyBaseEntry

logger = logging.getLogger(__name__)


class OntologyRepository(Protocol):
    """Repository Protocol - all Adapters must implement this interface."""

    def list_scenes(self, base_id: str) -> list[dict]: ...
    def get_scene(self, base_id: str, scene_id: str) -> dict | None: ...
    def get_objects(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None: ...
    def get_views(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_relations(self, base_id: str, scene_id: str) -> list[dict]: ...
    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict: ...
    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None: ...
    def search_instances(self, base_id: str, query: dict) -> dict: ...
    def search_ontology(self, base_id: str, scene_id: str, request: dict) -> dict: ...
    def graph_query(self, base_id: str, scene_id: str, query: dict) -> dict: ...


class OntologyService:
    """Ontology service - thin orchestration layer.

    Responsibilities:
        1. Look up Registry to determine sourceType
        2. Route to the correct Adapter
        3. Enforce write permission (REMOTE returns 403)
    """

    def __init__(
        self,
        registry: object,  # OntologyBaseRegistry | FakeRegistry
        local_adapter: object,  # OntologyRepository | Fake
        remote_adapter: object,  # OntologyRepository | Fake
    ) -> None:
        self._registry = registry
        self._local = local_adapter
        self._remote = remote_adapter

    # -- OntologyBase CRUD --

    def list_bases(self) -> list[dict]:
        entries = self._registry.list()
        return [self._entry_to_dict(e) for e in entries]

    def create_base(self, data: dict) -> dict:
        source_url = data.get("sourceUrl")
        entry = OntologyBaseEntry(
            base_id=data["baseId"],
            display_name=data["displayName"],
            description=data.get("description", ""),
            owner_type=data.get("ownerType", "personal"),
            source_type="REMOTE" if source_url else "LOCAL",
            source_url=source_url,
            auth_type=data.get("authType"),
            auth_config=data.get("authConfig"),
            timeout_sec=data.get("timeoutSec", 30),
        )
        self._registry.register(entry)
        return self._entry_to_dict(entry)

    def delete_base(self, base_id: str) -> None:
        entry = self._registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        self._registry.unregister(base_id)

    # -- metadata: read --

    def list_scenes(self, base_id: str) -> list[dict]:
        self._ensure_exists(base_id)
        return self._local.list_scenes(base_id)

    def get_objects(
        self,
        base_id: str,
        scene_id: str,
        *,
        use_cache: bool = False,  # noqa: ARG002
    ) -> list[dict]:
        self._ensure_exists(base_id)
        return self._local.get_objects(base_id, scene_id)

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        self._ensure_exists(base_id)
        return self._local.get_object_detail(base_id, scene_id, object_code)

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        self._ensure_exists(base_id)
        return self._local.get_views(base_id, scene_id)

    # -- metadata: write --

    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict:
        entry = self._ensure_exists(base_id)
        if entry.source_type == "REMOTE":
            raise PermissionError("Remote ontology base is read-only")
        return self._local.create_object(base_id, scene_id, obj_data)

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        entry = self._ensure_exists(base_id)
        if entry.source_type == "REMOTE":
            raise PermissionError("Remote ontology base is read-only")
        self._local.delete_object(base_id, scene_id, object_code)

    # -- helpers --

    def _ensure_exists(self, base_id: str) -> OntologyBaseEntry:
        entry = self._registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        return entry

    @staticmethod
    def _entry_to_dict(entry: OntologyBaseEntry) -> dict:
        return {
            "baseId": entry.base_id,
            "displayName": entry.display_name,
            "description": entry.description,
            "sourceType": entry.source_type,
            "ownerType": entry.owner_type,
            "sourceUrl": entry.source_url,
            "authType": entry.auth_type,
            "timeoutSec": entry.timeout_sec,
            "createdAt": entry.created_at,
        }
