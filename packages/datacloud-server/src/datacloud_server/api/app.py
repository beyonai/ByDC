"""FastAPI application factory with dependency injection."""

# ruff: noqa: ARG002  # fallback adapter must match Protocol signatures — all params required by contract

from __future__ import annotations

from collections.abc import Mapping  # noqa: F401  # used in annotations under PEP 563
from typing import TYPE_CHECKING

from fastapi import FastAPI

from datacloud_server.api.routes import router
from datacloud_server.services.adapter_router import AdapterRouter
from datacloud_server.services.ontology_base_service import OntologyBaseService
from datacloud_server.services.ontology_resource_service import OntologyResourceService
from datacloud_server.services.ontology_search_service import OntologySearchService

if TYPE_CHECKING:
    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View
    from datacloud_server.ports.ontology_repository import OntologyRepository
    from datacloud_server.registry.registry import OntologyBaseRegistry


class _WriteRejectingFallback:
    """Write-rejecting fallback adapter used when no remote adapter is configured.

    Raises PermissionError on all write operations; returns empty on reads.
    """

    _ERR_MSG = "Remote ontology base is read-only"

    # ── Scene ──
    def list_scenes(self, base_id: str) -> list[dict]: return []  # type: ignore[empty-body]
    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]: return []  # type: ignore[empty-body]
    def count_scenes(self, base_id: str, keyword: str | None) -> int: return 0  # type: ignore[empty-body]
    def get_scene_details(
        self, base_id: str, scene_id: str, *,
        view_code: str | None = None, object_code: str | None = None,
    ) -> dict: return {}  # type: ignore[empty-body]
    def query_ontologies_by_scene(
        self, base_id: str, scene_id: str, *,
        page: int = 1, page_size: int = 20, keyword: str | None = None,
    ) -> dict: return {"data": [], "totalCount": 0}  # type: ignore[empty-body]

    # ── Object ──
    def get_objects(self, base_id: str, scene_id: str) -> list[dict]: return []  # type: ignore[empty-body]
    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None: return None  # type: ignore[empty-body]
    def create_object(self, base_id: str, scene_id: str, obj: ObjectType) -> ObjectType: raise PermissionError(self._ERR_MSG)
    def update_object(self, base_id: str, scene_id: str, object_code: str, obj: ObjectType) -> ObjectType: raise PermissionError(self._ERR_MSG)
    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None: raise PermissionError(self._ERR_MSG)

    # ── View ──
    def get_views(self, base_id: str, scene_id: str) -> list[dict]: return []  # type: ignore[empty-body]
    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None: return None  # type: ignore[empty-body]
    def create_view(self, base_id: str, scene_id: str, view: View) -> View: raise PermissionError(self._ERR_MSG)
    def update_view(self, base_id: str, scene_id: str, view_code: str, view: View) -> View: raise PermissionError(self._ERR_MSG)
    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None: raise PermissionError(self._ERR_MSG)

    # ── Relation ──
    def get_relations(self, base_id: str, scene_id: str) -> list[dict]: return []  # type: ignore[empty-body]
    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None: return None  # type: ignore[empty-body]
    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation: raise PermissionError(self._ERR_MSG)
    def update_relation(self, base_id: str, scene_id: str, rel_code: str, rel: Relation) -> Relation: raise PermissionError(self._ERR_MSG)
    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None: raise PermissionError(self._ERR_MSG)

    # ── Datasource ──
    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]: return []  # type: ignore[empty-body]
    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None: return None  # type: ignore[empty-body]
    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource: raise PermissionError(self._ERR_MSG)
    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None: raise PermissionError(self._ERR_MSG)

    # ── Action ──
    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]: return []  # type: ignore[empty-body]
    def get_action_detail(self, base_id: str, scene_id: str, object_code: str, action_code: str) -> dict | None: return None  # type: ignore[empty-body]
    def create_action(self, base_id: str, scene_id: str, object_code: str, action: Action) -> Action: raise PermissionError(self._ERR_MSG)
    def update_action(self, base_id: str, scene_id: str, object_code: str, action_code: str, action: Action) -> Action: raise PermissionError(self._ERR_MSG)
    def delete_action(self, base_id: str, scene_id: str, object_code: str, action_code: str) -> None: raise PermissionError(self._ERR_MSG)

    # ── Search & Graph ──
    def search_instances(self, base_id: str, *, object_code: str, select: list[str] | None = None, where: dict | None = None) -> dict:
        return {"data": [], "totalCount": 0}
    def search_ontology(self, base_id: str, scene_id: str, *, keyword: str, query_type: str = "vector", search_scope: str = "all", object_code: list[str] | None = None, view_code: list[str] | None = None, property_code: list[str] | None = None, result_per_type: int = 5, page_size: int = 20, page_token: str | None = None) -> dict:
        return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}
    def graph_query(self, base_id: str, scene_id: str, *, object_code: list[str], match_by: str = "name", values: list[str] | None = None, step: int = 1) -> dict:
        return {"nodes": [], "edges": []}
    def graph_path(self, base_id: str, scene_id: str, *, match_by: str = "name", start_node: str, end_node: str = "", direction: str = "forward") -> dict:
        return {"path": [], "edges": [], "hops": -1}

    # ── OWL Import ──
    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict: raise PermissionError(self._ERR_MSG)


def create_app(
    *,
    registry: OntologyBaseRegistry | None = None,
    adapters: dict[str, OntologyRepository] | None = None,
) -> FastAPI:
    """Create FastAPI app with optional dependency overrides for testing."""
    from datacloud_server.api import deps as _deps  # noqa: PLC0415

    app = FastAPI(title="Ontology Service", version="0.1.0")
    app.include_router(router)

    if registry is not None and adapters is not None:
        # Auto-inject write-rejecting fallback for REMOTE if not provided
        if "REMOTE" not in adapters:
            adapters["REMOTE"] = _WriteRejectingFallback()
        router_obj = AdapterRouter(registry=registry, adapters=adapters)
        _deps.set_services(
            base_service=OntologyBaseService(router_obj),
            resource_service=OntologyResourceService(router_obj),
            search_service=OntologySearchService(router_obj),
        )

    return app
