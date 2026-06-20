"""OntologyRepository Protocol — abstract interface for all ontology adapters.

All methods use typed parameters: domain models for CRUD, keyword parameters
for search/graph queries. No bare `dict` in any signature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View


class OntologyRepository(Protocol):
    """Repository Protocol - all Adapters must implement this interface."""

    # ── Scene ──
    def list_scenes(self, base_id: str) -> list[dict]: ...
    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]: ...
    def count_scenes(self, base_id: str, keyword: str | None) -> int: ...
    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict: ...
    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict: ...

    # ── Object ──
    def get_objects(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None: ...
    def create_object(self, base_id: str, scene_id: str, obj: ObjectType) -> ObjectType: ...
    def update_object(
        self, base_id: str, scene_id: str, object_code: str, obj: ObjectType
    ) -> ObjectType: ...
    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None: ...

    # ── View ──
    def get_views(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None: ...
    def create_view(self, base_id: str, scene_id: str, view: View) -> View: ...
    def update_view(self, base_id: str, scene_id: str, view_code: str, view: View) -> View: ...
    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None: ...

    # ── Relation ──
    def get_relations(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None: ...
    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation: ...
    def update_relation(
        self, base_id: str, scene_id: str, rel_code: str, rel: Relation
    ) -> Relation: ...
    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None: ...

    # ── Datasource ──
    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]: ...
    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None: ...
    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource: ...
    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None: ...

    # ── Action ──
    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]: ...
    def get_action_detail(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
    ) -> dict | None: ...
    def create_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action: Action,
    ) -> Action: ...
    def update_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        action: Action,
    ) -> Action: ...
    def delete_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
    ) -> None: ...

    # ── Search & Graph ──
    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict | None = None,
    ) -> dict: ...

    def search_ontology(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        result_per_type: int = 5,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> dict: ...

    def search_ontology_batch(
        self,
        base_id: str,
        scene_id: str,
        *,
        keywords: list[str],
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        result_per_type: int = 5,
    ) -> list[dict]: ...

    def graph_query(
        self,
        base_id: str,
        scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict: ...

    def graph_path(
        self,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict: ...

    # ── OWL Import ──
    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict: ...
