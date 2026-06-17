"""OntologyBaseService — OntologyBase management + Scene queries (8 methods).

Injects AdapterRouter only — no duplicated _get_adapter logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_server.registry.registry import OntologyBaseEntry
    from datacloud_server.services.adapter_router import AdapterRouter


class OntologyBaseService:
    """Manage OntologyBase lifecycle and Scene queries."""

    def __init__(self, router: AdapterRouter) -> None:
        self._router = router

    # -- OntologyBase CRUD --

    def list_bases(self) -> list[dict]:
        entries = self._router.registry.list()
        return [self._entry_to_dict(e) for e in entries]

    def create_base(self, entry: OntologyBaseEntry) -> dict:
        self._router.registry.register(entry)
        return self._entry_to_dict(entry)

    def delete_base(self, base_id: str) -> None:
        entry = self._router.registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        self._router.registry.unregister(base_id)

    # -- Scene: query + detail --

    def list_scenes(self, base_id: str) -> list[dict]:
        return self._router.get(base_id).list_scenes(base_id)

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]:
        return self._router.get(base_id).query_scenes(base_id, keyword)

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        return self._router.get(base_id).count_scenes(base_id, keyword)

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict:
        return self._router.get(base_id).get_scene_details(
            base_id,
            scene_id,
            view_code=view_code,
            object_code=object_code,
        )

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict:
        return self._router.get(base_id).query_ontologies_by_scene(
            base_id,
            scene_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
        )

    # -- helpers --

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
