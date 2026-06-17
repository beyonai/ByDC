"""OntologySearchService — instance search + graph query + unified search + OWL import (6 methods).

Injects AdapterRouter only — no duplicated _get_adapter logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_server.services.adapter_router import AdapterRouter


class OntologySearchService:
    """Instance search, graph traversal, unified ontology search, and OWL import."""

    def __init__(self, router: AdapterRouter) -> None:
        self._router = router

    def search_instances(
        self, base_id: str, *,
        object_code: str,
        select: list[str] | None = None,
        where: dict | None = None,
    ) -> dict:
        return self._router.get(base_id).search_instances(
            base_id, object_code=object_code, select=select, where=where,
        )

    def search_ontology(
        self, base_id: str, scene_id: str, *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        result_per_type: int = 5,
    ) -> dict:
        return self._router.get(base_id).search_ontology(
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
        return self._router.get(base_id).search_ontology_base(
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
        return self._router.get(base_id).graph_query(
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
        return self._router.get(base_id).graph_path(
            base_id, scene_id,
            match_by=match_by, start_node=start_node, end_node=end_node, direction=direction,
        )

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        """Import OWL definitions from a ZIP file (LOCAL only)."""
        return self._router.get(base_id).import_owl(base_id, scene_id, zip_bytes)
