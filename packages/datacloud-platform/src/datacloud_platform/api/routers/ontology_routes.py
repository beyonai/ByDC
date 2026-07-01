"""OntologyBase + Scene CRUD routes (factory pattern).

Prefix: ``/api/v1/ontologyBases``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from datacloud_platform.base_entry import (
    OntologyBaseEntry,
    generate_snowflake,
    validate_base_id,
)
from datacloud_platform.models.base_entry import OntologyBaseCreate, OntologyBaseUpdate
from datacloud_platform.models.common import ok
from datacloud_platform.models.scene import (
    SceneCreate,
    SceneMembersRequest,
    SceneUpdate,
)
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _parse_csv(param: str | None) -> list[str] | None:
    """Split a comma-separated query string into a list, or return None if empty."""
    if param is None or not param.strip():
        return None
    return [v.strip() for v in param.split(",") if v.strip()]


def create_ontology_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for ontology-base + scene endpoints.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases")

    # ══════════════════════════════════════════════════
    # OntologyBase management
    # ══════════════════════════════════════════════════

    @router.get("", tags=["OntologyBase"])
    def list_bases(
        keyword: str | None = Query(
            default=None, description="模糊查询本体库名称/描述/ID"
        ),
    ) -> Any:
        """List all ontology bases. Optionally filter by keyword."""
        return ok(data=platform.list_bases(keyword=keyword))

    @router.get("/{owner_type}", tags=["OntologyBase"])
    def list_bases_by_owner(
        owner_type: str,
        keyword: str | None = Query(
            default=None, description="模糊查询本体库名称/描述/ID"
        ),
    ) -> Any:
        """List ontology bases filtered by owner_type. Optionally filter by keyword."""
        return ok(data=platform.list_bases(owner_type=owner_type, keyword=keyword))

    @router.post("", tags=["OntologyBase"])
    def create_base(body: OntologyBaseCreate) -> Any:
        """Create an ontology base.

        - ``baseId`` is optional — a snowflake ID is generated when omitted.
        - When provided, it must match ``^[a-z][a-z0-9_-]{{0,15}}$``.
        - Duplicate ``baseId`` returns 409.
        - sourceType is auto-derived: sourceUrl present → REMOTE, else LOCAL.
        """
        base_id = body.base_id
        if base_id is not None:
            if not validate_base_id(base_id):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid baseId '{base_id}': must match "
                    f"'^[a-z][a-z0-9_-]{{0,15}}$' (lowercase letter first, "
                    f"1-16 chars, only a-z, 0-9, _, -)",
                )
            if platform.base_exists(base_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"OntologyBase '{base_id}' already exists",
                )
        else:
            base_id = generate_snowflake()

        source_url = body.source_url
        entry = OntologyBaseEntry(
            base_id=base_id,
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

    @router.delete("/{base_id}", tags=["OntologyBase"])
    def delete_base(base_id: str) -> Any:
        """Delete an ontology base."""
        try:
            platform.delete_base(base_id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/{base_id}", tags=["OntologyBase"])
    def update_base(base_id: str, body: OntologyBaseUpdate) -> Any:
        """Update an ontology base.

        Only the fields provided in the request body are updated.
        ``baseId`` is read-only — passing it has no effect.
        """
        try:
            result = platform.update_base(base_id, body)
            return ok(data=result, message="updated")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Scene query + detail
    # ══════════════════════════════════════════════════

    @router.get("/{base_id}/scenes", tags=["Scene"])
    def list_scenes(
        base_id: str,
        keyword: str | None = Query(default=None, description="模糊查询场景列表"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List scenes under an ontology base. Supports optional keyword filter."""
        try:
            if keyword:
                return ok(
                    data=platform.query_scenes(base_id, keyword, cache_mode=cache_mode),
                    totalCount=platform.count_scenes(
                        base_id, keyword, cache_mode=cache_mode
                    ),
                )
            return ok(data=platform.list_scenes(base_id, cache_mode=cache_mode))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{base_id}/scenes/{scene_id}", tags=["Scene"])
    def get_scene_details(
        base_id: str,
        scene_id: str,
        view_code: str | None = Query(
            default=None, alias="viewCode", description="逗号分隔"
        ),
        object_code: str | None = Query(
            default=None, alias="objectCode", description="逗号分隔"
        ),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get scene details with optional associated resource filtering."""
        try:
            result = platform.get_scene_details(
                base_id,
                scene_id,
                view_code=_parse_csv(view_code),
                object_code=_parse_csv(object_code),
                cache_mode=cache_mode,
            )
            return ok(data=result)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{base_id}/scenes/{scene_id}/ontologies", tags=["Scene"])
    def query_ontologies_by_scene(
        base_id: str,
        scene_id: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Query ontologies in a scene."""
        try:
            result = platform.query_ontologies_by_scene(
                base_id,
                scene_id,
                page=page,
                page_size=page_size,
                keyword=keyword,
                cache_mode=cache_mode,
            )
            return ok(data=result["data"], totalCount=result["totalCount"])
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Scene CRUD
    # ══════════════════════════════════════════════════

    @router.post("/{base_id}/scenes", tags=["Scene"])
    def create_scene(base_id: str, body: SceneCreate) -> Any:
        """Create a scene (grouping container) under a base."""
        try:
            result = platform.create_scene(base_id, body)
            return ok(data=result, message="created")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/{base_id}/scenes/{scene_id}", tags=["Scene"])
    def update_scene(base_id: str, scene_id: str, body: SceneUpdate) -> Any:
        """Update scene metadata."""
        try:
            result = platform.update_scene(base_id, scene_id, body)
            return ok(data=result, message="updated")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/{base_id}/scenes/{scene_id}", tags=["Scene"])
    def delete_scene(base_id: str, scene_id: str) -> Any:
        """Delete a scene — does NOT delete member resources."""
        try:
            platform.delete_scene(base_id, scene_id)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Scene member management
    # ══════════════════════════════════════════════════

    @router.post("/{base_id}/scenes/{scene_id}/members", tags=["Scene"])
    def add_scene_members(
        base_id: str, scene_id: str, body: SceneMembersRequest
    ) -> Any:
        """Add objects/views to a scene (idempotent)."""
        try:
            result = platform.add_scene_members(
                base_id, scene_id, body.object_codes, body.view_codes
            )
            return ok(data=result, message="members added")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/{base_id}/scenes/{scene_id}/members", tags=["Scene"])
    def remove_scene_members(
        base_id: str, scene_id: str, body: SceneMembersRequest
    ) -> Any:
        """Remove objects/views from a scene — does NOT delete resources."""
        try:
            result = platform.remove_scene_members(
                base_id, scene_id, body.object_codes, body.view_codes
            )
            return ok(data=result, message="members removed")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
