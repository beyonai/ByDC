"""Object / View / Relation / Action / Datasource CRUD routes (factory pattern).

Resources are base-level — base_id is a query parameter, not a path parameter.

Shared prefix: ``/api/v1/ontologyBases``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from datacloud_platform.models.action import Action
from datacloud_platform.models.common import ok
from datacloud_platform.models.datasource import Datasource
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _parse_csv(param: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, ignoring blanks."""
    if param is None or not param.strip():
        return None
    return [v.strip() for v in param.split(",") if v.strip()]


def create_resource_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for Object / View / Relation / Action / Datasource CRUD.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases")

    # ══════════════════════════════════════════════════
    # Object CRUD (flat routes — base_id as query param)
    # ══════════════════════════════════════════════════

    @router.get("/objects", tags=["Object"])
    def list_objects(
        base_id: str = Query(default="default"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        owner_type: str | None = Query(default=None, alias="ownerType"),
        user_code: str | None = Query(default=None, alias="userCode"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List objects in a base."""
        _ = (page, page_size, owner_type, user_code, keyword)
        try:
            return ok(data=platform.get_objects(base_id, cache_mode=cache_mode))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/objects/{code}", tags=["Object"])
    def get_object(
        code: str,
        base_id: str = Query(default="default"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get object detail."""
        try:
            obj = platform.get_object_detail(base_id, code, cache_mode=cache_mode)
            if obj is None:
                raise HTTPException(
                    status_code=404, detail=f"Object '{code}' not found"
                )
            return ok(data=obj)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/objects", tags=["Object"])
    def create_object(
        body: ObjectType,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Create an object (LOCAL only). Auto-added to default scene when no scene specified."""
        try:
            return ok(
                data=platform.create_object_with_scene(base_id, body), message="created"
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/objects/{code}", tags=["Object"])
    def update_object(
        code: str,
        body: ObjectType,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Update an object (LOCAL only)."""
        try:
            platform.update_object(base_id, code, body)
            return ok(data={"objectCode": code})
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/objects/{code}", tags=["Object"])
    def delete_object(
        code: str,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Delete an object (LOCAL only). Removes from all scenes before deletion."""
        try:
            platform.delete_object_from_all_scenes(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # View CRUD (flat routes — base_id as query param)
    # ══════════════════════════════════════════════════

    @router.get("/views", tags=["View"])
    def list_views(
        base_id: str = Query(default="default"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        owner_type: str | None = Query(default=None, alias="ownerType"),
        user_code: str | None = Query(default=None, alias="userCode"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List views in a base."""
        _ = (page, page_size, owner_type, user_code, keyword)
        try:
            return ok(data=platform.get_views(base_id, cache_mode=cache_mode))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/views/{code}", tags=["View"])
    def get_view(
        code: str,
        base_id: str = Query(default="default"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get view detail."""
        try:
            view = platform.get_view_detail(base_id, code, cache_mode=cache_mode)
            if view is None:
                raise HTTPException(status_code=404, detail=f"View '{code}' not found")
            return ok(data=view)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/views", tags=["View"])
    def create_view(
        body: View,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Create a view (LOCAL only). Auto-added to default scene when no scene specified."""
        try:
            return ok(
                data=platform.create_view_with_scene(base_id, body), message="created"
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/views/{code}", tags=["View"])
    def update_view(
        code: str,
        body: View,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Update a view (LOCAL only)."""
        try:
            platform.update_view(base_id, code, body)
            return ok(data={"viewCode": code})
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/views/{code}", tags=["View"])
    def delete_view(
        code: str,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Delete a view (LOCAL only). Removes from all scenes before deletion."""
        try:
            platform.delete_view_from_all_scenes(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Relation CRUD (flat routes — base_id as query param)
    # ══════════════════════════════════════════════════

    @router.get("/relations", tags=["Relation"])
    def list_relations(
        base_id: str = Query(default="default"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        owner_type: str | None = Query(default=None, alias="ownerType"),
        user_code: str | None = Query(default=None, alias="userCode"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List relations in a base."""
        _ = (page, page_size, owner_type, user_code, keyword)
        try:
            return ok(data=platform.get_relations(base_id, cache_mode=cache_mode))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/relations/{code}", tags=["Relation"])
    def get_relation(
        code: str,
        base_id: str = Query(default="default"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get relation detail."""
        try:
            rel = platform.get_relation_detail(base_id, code, cache_mode=cache_mode)
            if rel is None:
                raise HTTPException(
                    status_code=404, detail=f"Relation '{code}' not found"
                )
            return ok(data=rel)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/relations", tags=["Relation"])
    def create_relation(
        body: Relation,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Create a relation (LOCAL only)."""
        try:
            return ok(
                data=platform.create_relation(base_id, body),
                message="created",
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/relations/{code}", tags=["Relation"])
    def update_relation(
        code: str,
        body: Relation,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Update a relation (LOCAL only)."""
        try:
            platform.update_relation(base_id, code, body)
            return ok(data={"relationCode": code})
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/relations/{code}", tags=["Relation"])
    def delete_relation(
        code: str,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Delete a relation (LOCAL only)."""
        try:
            platform.delete_relation(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Datasource CRUD (flat routes — base_id as query param)
    # ══════════════════════════════════════════════════

    @router.get("/datasources", tags=["Datasource"])
    def list_datasources(
        base_id: str = Query(default="default"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        owner_type: str | None = Query(default=None, alias="ownerType"),
        user_code: str | None = Query(default=None, alias="userCode"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List datasources in a base."""
        _ = (page, page_size, owner_type, user_code, keyword)
        try:
            return ok(data=platform.get_datasources(base_id, cache_mode=cache_mode))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/datasources/{db_id}", tags=["Datasource"])
    def get_datasource(
        db_id: str,
        base_id: str = Query(default="default"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get datasource detail."""
        try:
            ds = platform.get_datasource_detail(base_id, db_id, cache_mode=cache_mode)
            if ds is None:
                raise HTTPException(
                    status_code=404, detail=f"Datasource '{db_id}' not found"
                )
            return ok(data=ds)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/datasources", tags=["Datasource"])
    def create_datasource(
        body: Datasource,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Create a datasource (LOCAL only)."""
        try:
            return ok(
                data=platform.create_datasource(base_id, body),
                message="created",
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/datasources/{db_id}", tags=["Datasource"])
    def delete_datasource(
        db_id: str,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Delete a datasource (LOCAL only)."""
        try:
            platform.delete_datasource(base_id, db_id)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Action CRUD (flat routes — base_id as query param)
    # ══════════════════════════════════════════════════

    @router.get("/objects/{object_code}/actions", tags=["Action"])
    def list_actions(
        object_code: str,
        base_id: str = Query(default="default"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
        owner_type: str | None = Query(default=None, alias="ownerType"),
        user_code: str | None = Query(default=None, alias="userCode"),
        keyword: str | None = Query(default=None),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """List actions on an object."""
        _ = (page, page_size, owner_type, user_code, keyword)
        try:
            return ok(
                data=platform.get_actions(base_id, object_code, cache_mode=cache_mode)
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/objects/{object_code}/actions/{code}", tags=["Action"])
    def get_action(
        object_code: str,
        code: str,
        base_id: str = Query(default="default"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get action detail."""
        try:
            action = platform.get_action_detail(
                base_id, object_code, code, cache_mode=cache_mode
            )
            if action is None:
                raise HTTPException(
                    status_code=404, detail=f"Action '{code}' not found"
                )
            return ok(data=action)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/objects/{object_code}/actions", tags=["Action"])
    def create_action(
        object_code: str,
        body: Action,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Create an action on an object (LOCAL only)."""
        try:
            return ok(
                data=platform.create_action(base_id, object_code, body),
                message="created",
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/objects/{object_code}/actions/{code}", tags=["Action"])
    def update_action(
        object_code: str,
        code: str,
        body: Action,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Update an action on an object (LOCAL only)."""
        try:
            platform.update_action(base_id, object_code, code, body)
            return ok(data={"actionCode": code})
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/objects/{object_code}/actions/{code}", tags=["Action"])
    def delete_action(
        object_code: str,
        code: str,
        base_id: str = Query(default="default"),
    ) -> Any:
        """Delete an action from an object (LOCAL only)."""
        try:
            platform.delete_action(base_id, object_code, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Term bindings (object / view)
    # ══════════════════════════════════════════════════

    @router.get("/objects/{object_code}/term-bindings", tags=["Object"])
    def get_object_term_bindings(
        object_code: str,
        base_id: str = Query(default="default"),
        term_master_type: str | None = Query(default=None),
        property_codes: str | None = Query(default=None, alias="propertyCodes"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get term type bindings on an object's properties."""
        try:
            return ok(
                data=platform.get_object_property_term_bindings(
                    base_id,
                    object_code,
                    term_master_type=term_master_type,
                    property_codes=_parse_csv(property_codes),
                    cache_mode=cache_mode,
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/views/{view_code}/term-bindings", tags=["View"])
    def get_view_term_bindings(
        view_code: str,
        base_id: str = Query(default="default"),
        term_master_type: str | None = Query(default=None),
        property_codes: str | None = Query(default=None, alias="propertyCodes"),
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> Any:
        """Get term type bindings on a view's properties."""
        try:
            return ok(
                data=platform.get_view_property_term_bindings(
                    base_id,
                    view_code,
                    term_master_type=term_master_type,
                    property_codes=_parse_csv(property_codes),
                    cache_mode=cache_mode,
                )
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
