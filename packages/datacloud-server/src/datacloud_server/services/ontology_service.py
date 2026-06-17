"""OntologyService - service layer orchestration + adapter routing.

Thin orchestration: DI (Registry + Repository), routing + permission check.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View
    from datacloud_server.ports.ontology_repository import OntologyRepository
    from datacloud_server.registry.registry import OntologyBaseEntry

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

    def create_base(self, entry: OntologyBaseEntry) -> dict:
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

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
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
        self, base_id: str, scene_id: str, object_code: str, action_code: str,
    ) -> dict | None:
        return self._get_adapter(base_id).get_action_detail(
            base_id, scene_id, object_code, action_code,
        )

    # -- metadata: write --

    def create_object(self, base_id: str, scene_id: str, obj: ObjectType) -> ObjectType:
        return self._get_adapter(base_id).create_object(base_id, scene_id, obj)

    def update_object(self, base_id: str, scene_id: str, object_code: str, obj: ObjectType) -> ObjectType:
        return self._get_adapter(base_id).update_object(base_id, scene_id, object_code, obj)

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        self._get_adapter(base_id).delete_object(base_id, scene_id, object_code)

    def create_view(self, base_id: str, scene_id: str, view: View) -> View:
        return self._get_adapter(base_id).create_view(base_id, scene_id, view)

    def update_view(self, base_id: str, scene_id: str, view_code: str, view: View) -> View:
        return self._get_adapter(base_id).update_view(base_id, scene_id, view_code, view)

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        self._get_adapter(base_id).delete_view(base_id, scene_id, view_code)

    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation:
        return self._get_adapter(base_id).create_relation(base_id, scene_id, rel)

    def update_relation(self, base_id: str, scene_id: str, rel_code: str, rel: Relation) -> Relation:
        return self._get_adapter(base_id).update_relation(base_id, scene_id, rel_code, rel)

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        self._get_adapter(base_id).delete_relation(base_id, scene_id, rel_code)

    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource:
        return self._get_adapter(base_id).create_datasource(base_id, scene_id, ds)

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        self._get_adapter(base_id).delete_datasource(base_id, scene_id, db_id)

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action: Action,
    ) -> Action:
        return self._get_adapter(base_id).create_action(
            base_id, scene_id, object_code, action,
        )

    def update_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str, action: Action,
    ) -> Action:
        return self._get_adapter(base_id).update_action(
            base_id, scene_id, object_code, action_code, action,
        )

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str,
    ) -> None:
        self._get_adapter(base_id).delete_action(
            base_id, scene_id, object_code, action_code,
        )

    # -- OWL import --

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        """Import OWL definitions from a ZIP file (LOCAL only)."""
        return self._get_adapter(base_id).import_owl(base_id, scene_id, zip_bytes)

    # -- application services: search & graph --

    def search_instances(
        self, base_id: str, *,
        object_code: str,
        select: list[str] | None = None,
        where: dict | None = None,
    ) -> dict:
        return self._get_adapter(base_id).search_instances(
            base_id, object_code=object_code, select=select, where=where,
        )

    def search_ontology(
        self, base_id: str, scene_id: str, *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        result_per_type: int = 5,
    ) -> dict:
        return self._get_adapter(base_id).search_ontology(
            base_id, scene_id,
            keyword=keyword, query_type=query_type,
            search_scope=search_scope, result_per_type=result_per_type,
        )

    def search_ontology_base(
        self, base_id: str, *,
        keyword: str,
        scene_id: str = "-1",
        query_type: str = "vector",
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        result_per_type: int = 5,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> dict:
        return self._get_adapter(base_id).search_ontology_base(
            base_id,
            keyword=keyword, scene_id=scene_id, query_type=query_type,
            search_scope=search_scope, object_code=object_code,
            view_code=view_code, property_code=property_code,
            result_per_type=result_per_type, page_size=page_size, page_token=page_token,
        )

    def graph_query(
        self, base_id: str, scene_id: str, *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict:
        return self._get_adapter(base_id).graph_query(
            base_id, scene_id,
            object_code=object_code, match_by=match_by, values=values, step=step,
        )

    def graph_path(
        self, base_id: str, scene_id: str, *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict:
        return self._get_adapter(base_id).graph_path(
            base_id, scene_id,
            match_by=match_by, start_node=start_node, end_node=end_node, direction=direction,
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
