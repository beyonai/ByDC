"""Object / View / Relation / Action / Datasource CRUD routes (factory pattern).

Resources are base-level — no longer scoped under a scene.

Shared prefix: ``/api/v1/ontologyBases/{owner_type}/{base_id}``
"""

# ruff: noqa: ARG001  # owner_type is a URL path parameter for routing, not consumed by services

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from datacloud_platform.models.action import Action
from datacloud_platform.models.common import ok
from datacloud_platform.models.datasource import Datasource
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def create_resource_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for Object / View / Relation / Action / Datasource CRUD.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``, tags ``["resources"]``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases", tags=["resources"])

    # ══════════════════════════════════════════════════
    # Object CRUD (base-level)
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/objects")
    def list_objects(owner_type: str, base_id: str) -> Any:
        """List objects in a base."""
        try:
            return ok(data=platform.get_objects(base_id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/objects/{code}")
    def get_object(owner_type: str, base_id: str, code: str) -> Any:
        """Get object detail."""
        try:
            obj = platform.get_object_detail(base_id, code)
            if obj is None:
                raise HTTPException(
                    status_code=404, detail=f"Object '{code}' not found"
                )
            return ok(data=obj)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{owner_type}/{base_id}/objects")
    def create_object(owner_type: str, base_id: str, body: ObjectType) -> Any:
        """Create an object (LOCAL only)."""
        try:
            return ok(data=platform.create_object(base_id, body), message="created")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/{owner_type}/{base_id}/objects/{code}")
    def update_object(
        owner_type: str, base_id: str, code: str, body: ObjectType
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

    @router.delete("/{owner_type}/{base_id}/objects/{code}")
    def delete_object(owner_type: str, base_id: str, code: str) -> Any:
        """Delete an object (LOCAL only)."""
        try:
            platform.delete_object(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # View CRUD (base-level)
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/views")
    def list_views(owner_type: str, base_id: str) -> Any:
        """List views in a base."""
        try:
            return ok(data=platform.get_views(base_id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/views/{code}")
    def get_view(owner_type: str, base_id: str, code: str) -> Any:
        """Get view detail."""
        try:
            view = platform.get_view_detail(base_id, code)
            if view is None:
                raise HTTPException(status_code=404, detail=f"View '{code}' not found")
            return ok(data=view)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{owner_type}/{base_id}/views")
    def create_view(owner_type: str, base_id: str, body: View) -> Any:
        """Create a view (LOCAL only)."""
        try:
            return ok(data=platform.create_view(base_id, body), message="created")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/{owner_type}/{base_id}/views/{code}")
    def update_view(owner_type: str, base_id: str, code: str, body: View) -> Any:
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

    @router.delete("/{owner_type}/{base_id}/views/{code}")
    def delete_view(owner_type: str, base_id: str, code: str) -> Any:
        """Delete a view (LOCAL only)."""
        try:
            platform.delete_view(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Relation CRUD (base-level)
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/relations")
    def list_relations(owner_type: str, base_id: str) -> Any:
        """List relations in a base."""
        try:
            return ok(data=platform.get_relations(base_id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/relations/{code}")
    def get_relation(owner_type: str, base_id: str, code: str) -> Any:
        """Get relation detail."""
        try:
            rel = platform.get_relation_detail(base_id, code)
            if rel is None:
                raise HTTPException(
                    status_code=404, detail=f"Relation '{code}' not found"
                )
            return ok(data=rel)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{owner_type}/{base_id}/relations")
    def create_relation(owner_type: str, base_id: str, body: Relation) -> Any:
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

    @router.put("/{owner_type}/{base_id}/relations/{code}")
    def update_relation(
        owner_type: str, base_id: str, code: str, body: Relation
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

    @router.delete("/{owner_type}/{base_id}/relations/{code}")
    def delete_relation(owner_type: str, base_id: str, code: str) -> Any:
        """Delete a relation (LOCAL only)."""
        try:
            platform.delete_relation(base_id, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Datasource CRUD (base-level)
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/datasources")
    def list_datasources(owner_type: str, base_id: str) -> Any:
        """List datasources in a base."""
        try:
            return ok(data=platform.get_datasources(base_id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/datasources/{db_id}")
    def get_datasource(owner_type: str, base_id: str, db_id: str) -> Any:
        """Get datasource detail."""
        try:
            ds = platform.get_datasource_detail(base_id, db_id)
            if ds is None:
                raise HTTPException(
                    status_code=404, detail=f"Datasource '{db_id}' not found"
                )
            return ok(data=ds)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{owner_type}/{base_id}/datasources")
    def create_datasource(owner_type: str, base_id: str, body: Datasource) -> Any:
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

    @router.delete("/{owner_type}/{base_id}/datasources/{db_id}")
    def delete_datasource(owner_type: str, base_id: str, db_id: str) -> Any:
        """Delete a datasource (LOCAL only)."""
        try:
            platform.delete_datasource(base_id, db_id)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Action CRUD (base-level, under object)
    # ══════════════════════════════════════════════════

    @router.get("/{owner_type}/{base_id}/objects/{object_code}/actions")
    def list_actions(owner_type: str, base_id: str, object_code: str) -> Any:
        """List actions on an object."""
        try:
            return ok(data=platform.get_actions(base_id, object_code))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/{owner_type}/{base_id}/objects/{object_code}/actions/{code}")
    def get_action(owner_type: str, base_id: str, object_code: str, code: str) -> Any:
        """Get action detail."""
        try:
            action = platform.get_action_detail(base_id, object_code, code)
            if action is None:
                raise HTTPException(
                    status_code=404, detail=f"Action '{code}' not found"
                )
            return ok(data=action)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{owner_type}/{base_id}/objects/{object_code}/actions")
    def create_action(
        owner_type: str,
        base_id: str,
        object_code: str,
        body: Action,
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

    @router.put("/{owner_type}/{base_id}/objects/{object_code}/actions/{code}")
    def update_action(
        owner_type: str,
        base_id: str,
        object_code: str,
        code: str,
        body: Action,
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

    @router.delete("/{owner_type}/{base_id}/objects/{object_code}/actions/{code}")
    def delete_action(
        owner_type: str, base_id: str, object_code: str, code: str
    ) -> Any:
        """Delete an action from an object (LOCAL only)."""
        try:
            platform.delete_action(base_id, object_code, code)
            return ok(message="deleted")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
