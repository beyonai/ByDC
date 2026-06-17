"""OntologyService - service layer orchestration + adapter routing.

Thin orchestration: DI (Registry + Repository), routing + permission check.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from datacloud_server.registry.registry import OntologyBaseEntry

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datacloud_server.ports.ontology_repository import OntologyRepository

logger = logging.getLogger(__name__)


class OntologyService:
    """Ontology service - thin orchestration layer.

    Responsibilities:
        1. Look up Registry to determine sourceType
        2. Route to the correct Adapter via _get_adapter()
    """

    def __init__(self, registry: object, adapters: Mapping[str, OntologyRepository]) -> None:
        """Create OntologyService with injected registry and adapters.

        Args:
            registry: OntologyBaseRegistry | FakeRegistry
            adapters: sourceType → Adapter mapping, e.g. {"LOCAL": local, "REMOTE": remote}
        """
        self._registry = registry
        self._adapters = adapters

    def _get_adapter(self, base_id: str) -> OntologyRepository:
        """Look up Registry for sourceType, dispatch to correct Adapter.

        Falls back to the first available adapter if sourceType is unknown.
        """
        entry = self._registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        source_type = entry.source_type
        adapter = self._adapters.get(source_type)
        if adapter is not None:
            return adapter
        # Fallback: return first available adapter
        return next(iter(self._adapters.values()))

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

    # -- Scene: query + detail --

    def list_scenes(self, base_id: str) -> list[dict]:
        return self._get_adapter(base_id).list_scenes(base_id)

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]:
        return self._get_adapter(base_id).query_scenes(base_id, keyword)

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        return self._get_adapter(base_id).count_scenes(base_id, keyword)

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict:
        return self._get_adapter(base_id).get_scene_details(
            base_id, scene_id, view_code=view_code, object_code=object_code,
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
        return self._get_adapter(base_id).query_ontologies_by_scene(
            base_id, scene_id, page=page, page_size=page_size, keyword=keyword,
        )

    # -- metadata: read --

    def get_objects(
        self,
        base_id: str,
        scene_id: str,
        *,
        use_cache: bool = False,  # noqa: ARG002
    ) -> list[dict]:
        return self._get_adapter(base_id).get_objects(base_id, scene_id)

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        return self._get_adapter(base_id).get_object_detail(base_id, scene_id, object_code)

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        return self._get_adapter(base_id).get_views(base_id, scene_id)

    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None:
        return self._get_adapter(base_id).get_view_detail(base_id, scene_id, view_code)

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        return self._get_adapter(base_id).get_relations(base_id, scene_id)

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        return self._get_adapter(base_id).get_relation_detail(base_id, scene_id, rel_code)

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]:
        return self._get_adapter(base_id).get_datasources(base_id, scene_id)

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        return self._get_adapter(base_id).get_datasource_detail(base_id, scene_id, db_id)

    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]:
        return self._get_adapter(base_id).get_actions(base_id, scene_id, object_code)

    def get_action_detail(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict | None:
        return self._get_adapter(base_id).get_action_detail(
            base_id, scene_id, object_code, action_code
        )

    # -- metadata: write --

    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict:
        return self._get_adapter(base_id).create_object(base_id, scene_id, obj_data)

    def update_object(self, base_id: str, scene_id: str, object_code: str, obj_data: dict) -> dict:
        return self._get_adapter(base_id).update_object(base_id, scene_id, object_code, obj_data)

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        self._get_adapter(base_id).delete_object(base_id, scene_id, object_code)

    def create_view(self, base_id: str, scene_id: str, view_data: dict) -> dict:
        return self._get_adapter(base_id).create_view(base_id, scene_id, view_data)

    def update_view(self, base_id: str, scene_id: str, view_code: str, view_data: dict) -> dict:
        return self._get_adapter(base_id).update_view(base_id, scene_id, view_code, view_data)

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        self._get_adapter(base_id).delete_view(base_id, scene_id, view_code)

    def create_relation(self, base_id: str, scene_id: str, rel_data: dict) -> dict:
        return self._get_adapter(base_id).create_relation(base_id, scene_id, rel_data)

    def update_relation(self, base_id: str, scene_id: str, rel_code: str, rel_data: dict) -> dict:
        return self._get_adapter(base_id).update_relation(base_id, scene_id, rel_code, rel_data)

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        self._get_adapter(base_id).delete_relation(base_id, scene_id, rel_code)

    def create_datasource(self, base_id: str, scene_id: str, ds_data: dict) -> dict:
        return self._get_adapter(base_id).create_datasource(base_id, scene_id, ds_data)

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        self._get_adapter(base_id).delete_datasource(base_id, scene_id, db_id)

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action_data: dict
    ) -> dict:
        return self._get_adapter(base_id).create_action(
            base_id, scene_id, object_code, action_data
        )

    def update_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str, action_data: dict
    ) -> dict:
        return self._get_adapter(base_id).update_action(
            base_id, scene_id, object_code, action_code, action_data
        )

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        self._get_adapter(base_id).delete_action(
            base_id, scene_id, object_code, action_code
        )

    # -- OWL import --

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        """Import OWL definitions from a ZIP file (LOCAL only)."""
        return self._get_adapter(base_id).import_owl(base_id, scene_id, zip_bytes)

    # -- application services --

    def search_instances(self, base_id: str, query: dict) -> dict:
        return self._get_adapter(base_id).search_instances(base_id, query)

    def search_ontology(self, base_id: str, scene_id: str, request: dict) -> dict:
        return self._get_adapter(base_id).search_ontology(base_id, scene_id, request)

    def search_ontology_base(self, base_id: str, request: dict) -> dict:
        return self._get_adapter(base_id).search_ontology_base(base_id, request)

    def graph_query(self, base_id: str, scene_id: str, query: dict) -> dict:
        return self._get_adapter(base_id).graph_query(base_id, scene_id, query)

    def graph_path(self, base_id: str, scene_id: str, query: dict) -> dict:
        return self._get_adapter(base_id).graph_path(base_id, scene_id, query)

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
