"""Search + Graph query routes (factory pattern).

Prefix: ``/api/v1/ontologyBases``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def create_search_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for search, instance search, and graph endpoints.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases")

    @router.post("/{base_id}/search", tags=["Search"])
    def search_ontology_base(base_id: str, body: dict[str, Any]) -> Any:
        """Cross-scene ontology search. sceneId in body ('-1' for global)."""
        try:
            return ok(
                data=platform.search_ontology(
                    base_id,
                    body.get("sceneIds", ["-1"]),
                    keyword=body.get("keyword", ""),
                    query_type=body.get("queryType", "vector"),
                    search_scope=body.get("searchScope", "all"),
                    metadata_type=body.get("metadataType"),
                    object_code=body.get("objectCode"),
                    view_code=body.get("viewCode"),
                    property_code=body.get("propertyCode"),
                    result_per_type=body.get("resultPerType", 5),
                    top_k=body.get("topK", 20),
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception:
            import logging

            logging.getLogger(__name__).exception("search_ontology_base failed")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    @router.post("/{base_id}/scenes/{scene_id}/search", tags=["Search"])
    def search_ontology(base_id: str, scene_id: str, body: dict[str, Any]) -> Any:
        """Vector search across ontology metadata and instances."""
        try:
            return ok(
                data=platform.search_ontology(
                    base_id,
                    [scene_id],
                    keyword=body.get("keyword", ""),
                    query_type=body.get("queryType", "vector"),
                    search_scope=body.get("searchScope", "all"),
                    metadata_type=body.get("metadataType"),
                    object_code=body.get("objectCode"),
                    view_code=body.get("viewCode"),
                    property_code=body.get("propertyCode"),
                    result_per_type=body.get("resultPerType", 5),
                    top_k=body.get("topK", 20),
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception:
            import logging

            logging.getLogger(__name__).exception("search_ontology failed")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    @router.post("/{base_id}/instances/search", tags=["Instance"])
    def search_instances(base_id: str, body: dict[str, Any]) -> Any:
        """Search instances in a base."""
        try:
            return ok(
                data=platform.search_instances(
                    base_id,
                    object_code=body.get("objectCode", ""),
                    select=body.get("select"),
                    where=body.get("where"),
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{base_id}/scenes/{scene_id}/graph/query", tags=["Graph"])
    def graph_query(base_id: str, scene_id: str, body: dict[str, Any]) -> Any:
        """Query the graph of objects and relations."""
        try:
            return ok(
                data=platform.graph_query(
                    base_id,
                    scene_id,
                    object_code=body.get("objectCodes", body.get("objectCode", [])),
                    match_by=body.get("matchBy", "name"),
                    values=body.get("values"),
                    step=body.get("depth", body.get("step", 1)),
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{base_id}/scenes/{scene_id}/graph/path", tags=["Graph"])
    def graph_path(base_id: str, scene_id: str, body: dict[str, Any]) -> Any:
        """Find shortest path between two objects."""
        try:
            return ok(
                data=platform.graph_path(
                    base_id,
                    scene_id,
                    match_by=body.get("matchBy", "name"),
                    start_node=body.get("sourceObjectCode", ""),
                    end_node=body.get("targetObjectCode", ""),
                    direction=body.get("direction", "forward"),
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
