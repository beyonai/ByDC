"""OntologyBase + Scene CRUD routes (factory pattern).

Prefix: ``/api/v1/ontologyBases``
"""

# ruff: noqa: ARG001  # owner_type is a URL path parameter for routing, not consumed by services

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from datacloud_platform.base_entry import OntologyBaseEntry
from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


class OntologyBaseCreate(BaseModel):
    """Create ontology base request."""

    base_id: str = Field(alias="baseId")
    display_name: str = Field(alias="displayName")
    owner_type: str = Field(default="personal", alias="ownerType")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    auth_type: str | None = Field(default=None, alias="authType")
    auth_config: dict[str, Any] | None = Field(default=None, alias="authConfig")
    timeout_sec: int = Field(default=30, alias="timeoutSec")
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


def create_ontology_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for ontology-base + scene endpoints.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``, tags ``["ontology"]``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases", tags=["ontology"])

    # ══════════════════════════════════════════════════
    # OntologyBase management
    # ══════════════════════════════════════════════════

    @router.get("")
    def list_bases() -> Any:
        """List all ontology bases."""
        return ok(data=platform.list_bases())

    @router.post("")
    def create_base(body: OntologyBaseCreate) -> Any:
        """Create an ontology base.

        sourceType is auto-derived: sourceUrl present → REMOTE, else LOCAL.
        """
        try:
            source_url = body.source_url
            entry = OntologyBaseEntry(
                base_id=body.base_id,
                display_name=body.display_name,
                description=body.description,
                owner_type=body.owner_type,
                source_type="REMOTE" if source_url else "LOCAL",
                source_url=source_url,
                auth_type=body.auth_type,
                auth_config=body.auth_config,
                timeout_sec=body.timeout_sec,
            )
            return ok(data=platform.create_base(entry), message="created")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.delete("/{owner_type}/{base_id}")
    def delete_base(owner_type: str, base_id: str) -> Any:
        """Delete an ontology base."""
        try:
            platform.delete_base(base_id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Scene query + detail
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/scenes")
    def list_scenes(
        owner_type: str,
        base_id: str,
        keyword: str | None = Query(default=None, description="模糊查询场景列表"),
    ) -> Any:
        """List scenes under an ontology base. Supports optional keyword filter."""
        try:
            if keyword:
                return ok(
                    data=platform.query_scenes(base_id, keyword),
                    totalCount=platform.count_scenes(base_id, keyword),
                )
            return ok(data=platform.list_scenes(base_id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/scenes/{scene_id}")
    def get_scene_details(
        owner_type: str,
        base_id: str,
        scene_id: str,
        view_code: str | None = Query(
            default=None, alias="viewCode", description="逗号分隔"
        ),
        object_code: str | None = Query(
            default=None, alias="objectCode", description="逗号分隔"
        ),
    ) -> Any:
        """Get scene details with optional associated resource filtering."""
        try:
            result = platform.get_scene_details(
                base_id,
                scene_id,
                view_code=view_code,
                object_code=object_code,
            )
            return ok(data=result)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/scenes/{scene_id}/ontologies")
    def query_ontologies_by_scene(
        owner_type: str,
        base_id: str,
        scene_id: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        keyword: str | None = Query(default=None),
    ) -> Any:
        """Query ontologies in a scene."""
        try:
            result = platform.query_ontologies_by_scene(
                base_id, scene_id, page=page, page_size=page_size, keyword=keyword
            )
            return ok(data=result["data"], totalCount=result["totalCount"])
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
