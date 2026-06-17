"""FastAPI application factory with dependency injection."""
# ruff: noqa: ARG002  # stubs must match Protocol signatures

from __future__ import annotations

from collections.abc import Mapping  # noqa: F401  # used in annotations under PEP 563
from typing import TYPE_CHECKING

from fastapi import FastAPI

from datacloud_server.api.routes import router
from datacloud_server.services.ontology_service import OntologyService

if TYPE_CHECKING:
    from datacloud_server.ports.ontology_repository import OntologyRepository
    from datacloud_server.registry.registry import OntologyBaseRegistry


class _RemoteFallbackAdapter:
    """Write-rejecting fallback adapter used when no remote adapter is configured.

    Raises PermissionError on all write operations; returns empty on reads.
    """

    _ERR_MSG = "Remote ontology base is read-only"

    # -- read stubs --
    def list_scenes(self, base_id: str) -> list[dict]: return []
    def get_scene(self, base_id: str, scene_id: str) -> dict | None: return None
    def get_objects(self, base_id: str, scene_id: str) -> list[dict]: return []
    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None: return None
    def get_views(self, base_id: str, scene_id: str) -> list[dict]: return []
    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None: return None
    def get_relations(self, base_id: str, scene_id: str) -> list[dict]: return []
    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None: return None
    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]: return []
    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None: return None
    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]: return []
    def get_action_detail(self, base_id: str, scene_id: str, object_code: str, action_code: str) -> dict | None: return None
    def search_instances(self, base_id: str, query: dict) -> dict: return {"data": [], "totalCount": 0}
    def search_ontology(self, base_id: str, scene_id: str, request: dict) -> dict: return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}
    def graph_query(self, base_id: str, scene_id: str, query: dict) -> dict: return {"nodes": [], "edges": []}
    def graph_path(self, base_id: str, scene_id: str, query: dict) -> dict: return {"path": [], "edges": [], "hops": -1}

    # -- write rejections --
    def create_object(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)
    def delete_object(self, *args, **kwargs) -> None: raise PermissionError(self._ERR_MSG)
    def create_view(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)
    def delete_view(self, *args, **kwargs) -> None: raise PermissionError(self._ERR_MSG)
    def create_relation(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)
    def delete_relation(self, *args, **kwargs) -> None: raise PermissionError(self._ERR_MSG)
    def create_datasource(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)
    def delete_datasource(self, *args, **kwargs) -> None: raise PermissionError(self._ERR_MSG)
    def create_action(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)
    def delete_action(self, *args, **kwargs) -> None: raise PermissionError(self._ERR_MSG)
    def import_owl(self, *args, **kwargs) -> dict: raise PermissionError(self._ERR_MSG)


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
            adapters["REMOTE"] = _RemoteFallbackAdapter()
        service = OntologyService(registry=registry, adapters=adapters)
        _deps.set_service(service)

    return app
