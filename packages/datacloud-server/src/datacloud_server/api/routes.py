"""Ontology service REST API routes.

All responses: {code:200, success:true, message:"ok", data:...}
Request bodies validated via Pydantic v2 schemas.
All routes include {ownerType} prefix matching API docs.
"""

# ruff: noqa: ARG001  # owner_type is a URL path parameter for routing, not consumed by services

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from datacloud_server.api.deps import get_service
from datacloud_server.api.schemas import (
    OntologyBaseCreate,  # noqa: TC001
)
from datacloud_server.models.action import Action  # noqa: TC001
from datacloud_server.models.common import ok
from datacloud_server.models.datasource import Datasource  # noqa: TC001
from datacloud_server.models.object_type import ObjectType  # noqa: TC001
from datacloud_server.models.relation import Relation  # noqa: TC001
from datacloud_server.models.view import View  # noqa: TC001

router = APIRouter(prefix="/api/v1/ontologyBases", tags=["ontology"])


# ══════════════════════════════════════════════════
# OntologyBase management
# ══════════════════════════════════════════════════


@router.get("")
def list_bases():
    """List all ontology bases."""
    svc = get_service()
    return ok(data=svc.list_bases())


@router.post("")
def create_base(body: OntologyBaseCreate):
    """Create an ontology base.

    sourceType is auto-derived: sourceUrl present -> REMOTE, else LOCAL.
    """
    svc = get_service()
    try:
        return ok(data=svc.create_base(body.model_dump(by_alias=True)), message="created")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}")
def delete_base(owner_type: str, base_id: str):
    """Delete an ontology base."""
    svc = get_service()
    try:
        svc.delete_base(base_id)
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
):
    """List scenes under an ontology base. Supports optional keyword filter."""
    svc = get_service()
    try:
        if keyword:
            return ok(
                data=svc.query_scenes(base_id, keyword),
                totalCount=svc.count_scenes(base_id, keyword),
            )
        return ok(data=svc.list_scenes(base_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}")
def get_scene_details(
    owner_type: str,
    base_id: str,
    scene_id: str,
    view_code: str | None = Query(default=None, alias="viewCode", description="逗号分隔"),
    object_code: str | None = Query(default=None, alias="objectCode", description="逗号分隔"),
):
    """Get scene details with optional associated resource filtering.

    - viewCode: return only those views + their associated resources
    - objectCode: return only those objects + their associated actions/relations/dbsources (views empty)
    - neither: full dump
    """
    svc = get_service()
    try:
        result = svc.get_scene_details(
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
):
    """Query ontologies in a scene."""
    svc = get_service()
    try:
        result = svc.query_ontologies_by_scene(
            base_id, scene_id, page=page, page_size=page_size, keyword=keyword
        )
        return ok(data=result["data"], totalCount=result["totalCount"])
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# View CRUD
# ══════════════════════════════════════════════════


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/views")
def list_views(owner_type: str, base_id: str, scene_id: str):
    """List views in a scene."""
    svc = get_service()
    try:
        return ok(data=svc.get_views(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/views/{code}")
def get_view(owner_type: str, base_id: str, scene_id: str, code: str):
    """Get view detail."""
    svc = get_service()
    try:
        view = svc.get_view_detail(base_id, scene_id, code)
        if view is None:
            raise HTTPException(status_code=404, detail=f"View '{code}' not found")
        return ok(data=view)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/views")
def create_view(owner_type: str, base_id: str, scene_id: str, body: View):
    """Create a view (LOCAL only)."""
    svc = get_service()
    try:
        return ok(
            data=svc.create_view(base_id, scene_id, body.model_dump(by_alias=True)),
            message="created",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{owner_type}/{base_id}/scenes/{scene_id}/views/{code}")
def update_view(owner_type: str, base_id: str, scene_id: str, code: str, body: View):
    """Update a view (LOCAL only)."""
    svc = get_service()
    try:
        svc.update_view(base_id, scene_id, code, body.model_dump(by_alias=True))
        return ok(data={"viewCode": code})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}/scenes/{scene_id}/views/{code}")
def delete_view(owner_type: str, base_id: str, scene_id: str, code: str):
    """Delete a view (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_view(base_id, scene_id, code)
        return ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Relation CRUD
# ══════════════════════════════════════════════════


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/relations")
def list_relations(owner_type: str, base_id: str, scene_id: str):
    """List relations in a scene."""
    svc = get_service()
    try:
        return ok(data=svc.get_relations(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/relations/{code}")
def get_relation(owner_type: str, base_id: str, scene_id: str, code: str):
    """Get relation detail."""
    svc = get_service()
    try:
        rel = svc.get_relation_detail(base_id, scene_id, code)
        if rel is None:
            raise HTTPException(status_code=404, detail=f"Relation '{code}' not found")
        return ok(data=rel)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/relations")
def create_relation(owner_type: str, base_id: str, scene_id: str, body: Relation):
    """Create a relation (LOCAL only)."""
    svc = get_service()
    try:
        return ok(
            data=svc.create_relation(base_id, scene_id, body.model_dump(by_alias=True)),
            message="created",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{owner_type}/{base_id}/scenes/{scene_id}/relations/{code}")
def update_relation(owner_type: str, base_id: str, scene_id: str, code: str, body: Relation):
    """Update a relation (LOCAL only)."""
    svc = get_service()
    try:
        svc.update_relation(base_id, scene_id, code, body.model_dump(by_alias=True))
        return ok(data={"relationCode": code})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}/scenes/{scene_id}/relations/{code}")
def delete_relation(owner_type: str, base_id: str, scene_id: str, code: str):
    """Delete a relation (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_relation(base_id, scene_id, code)
        return ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Datasource CRUD
# ══════════════════════════════════════════════════


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/datasources")
def list_datasources(owner_type: str, base_id: str, scene_id: str):
    """List datasources in a scene."""
    svc = get_service()
    try:
        return ok(data=svc.get_datasources(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/datasources/{db_id}")
def get_datasource(owner_type: str, base_id: str, scene_id: str, db_id: str):
    """Get datasource detail."""
    svc = get_service()
    try:
        ds = svc.get_datasource_detail(base_id, scene_id, db_id)
        if ds is None:
            raise HTTPException(status_code=404, detail=f"Datasource '{db_id}' not found")
        return ok(data=ds)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/datasources")
def create_datasource(owner_type: str, base_id: str, scene_id: str, body: Datasource):
    """Create a datasource (LOCAL only)."""
    svc = get_service()
    try:
        return ok(
            data=svc.create_datasource(base_id, scene_id, body.model_dump(by_alias=True)),
            message="created",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}/scenes/{scene_id}/datasources/{db_id}")
def delete_datasource(owner_type: str, base_id: str, scene_id: str, db_id: str):
    """Delete a datasource (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_datasource(base_id, scene_id, db_id)
        return ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Object CRUD
# ══════════════════════════════════════════════════


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/objects")
def list_objects(owner_type: str, base_id: str, scene_id: str, cache: bool = False):
    """List objects in a scene."""
    svc = get_service()
    try:
        return ok(data=svc.get_objects(base_id, scene_id, use_cache=cache))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{code}")
def get_object(owner_type: str, base_id: str, scene_id: str, code: str):
    """Get object detail."""
    svc = get_service()
    try:
        obj = svc.get_object_detail(base_id, scene_id, code)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"Object '{code}' not found")
        return ok(data=obj)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/objects")
def create_object(owner_type: str, base_id: str, scene_id: str, body: ObjectType):
    """Create an object (LOCAL only)."""
    svc = get_service()
    try:
        return ok(
            data=svc.create_object(base_id, scene_id, body.model_dump(by_alias=True)),
            message="created",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{code}")
def update_object(owner_type: str, base_id: str, scene_id: str, code: str, body: ObjectType):
    """Update an object (LOCAL only)."""
    svc = get_service()
    try:
        svc.update_object(base_id, scene_id, code, body.model_dump(by_alias=True))
        return ok(data={"objectCode": code})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{code}")
def delete_object(owner_type: str, base_id: str, scene_id: str, code: str):
    """Delete an object (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_object(base_id, scene_id, code)
        return ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Action CRUD
# ══════════════════════════════════════════════════


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{object_code}/actions")
def list_actions(owner_type: str, base_id: str, scene_id: str, object_code: str):
    """List actions on an object."""
    svc = get_service()
    try:
        return ok(data=svc.get_actions(base_id, scene_id, object_code))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{object_code}/actions/{code}")
def get_action(owner_type: str, base_id: str, scene_id: str, object_code: str, code: str):
    """Get action detail."""
    svc = get_service()
    try:
        action = svc.get_action_detail(base_id, scene_id, object_code, code)
        if action is None:
            raise HTTPException(status_code=404, detail=f"Action '{code}' not found")
        return ok(data=action)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{object_code}/actions")
def create_action(owner_type: str, base_id: str, scene_id: str, object_code: str, body: Action):
    """Create an action on an object (LOCAL only)."""
    svc = get_service()
    try:
        return ok(
            data=svc.create_action(base_id, scene_id, object_code, body.model_dump(by_alias=True)),
            message="created",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{object_code}/actions/{code}")
def update_action(
    owner_type: str, base_id: str, scene_id: str, object_code: str, code: str, body: Action
):
    """Update an action on an object (LOCAL only)."""
    svc = get_service()
    try:
        svc.update_action(base_id, scene_id, object_code, code, body.model_dump(by_alias=True))
        return ok(data={"actionCode": code})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{owner_type}/{base_id}/scenes/{scene_id}/objects/{object_code}/actions/{code}")
def delete_action(owner_type: str, base_id: str, scene_id: str, object_code: str, code: str):
    """Delete an action from an object (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_action(base_id, scene_id, object_code, code)
        return ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Search
# ══════════════════════════════════════════════════


@router.post("/{owner_type}/{base_id}/search")
def search_ontology_base(
    owner_type: str,
    base_id: str,
    body: dict,
):
    """Cross-scene ontology search. sceneId in body ('-1' for global)."""
    svc = get_service()
    try:
        return ok(data=svc.search_ontology_base(base_id, body))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/search")
def search_ontology(owner_type: str, base_id: str, scene_id: str, body: dict):
    """Vector search across ontology metadata and instances."""
    svc = get_service()
    try:
        return ok(data=svc.search_ontology(base_id, scene_id, body))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# OWL import
# ══════════════════════════════════════════════════


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/import-owl")
async def import_owl(
    owner_type: str,
    base_id: str,
    scene_id: str,
    file: UploadFile = File(...),  # noqa: B008
):
    """Import OWL definitions from a ZIP file (LOCAL only).

    Expects multipart upload with Content-Type: application/zip.
    """
    svc = get_service()
    try:
        zip_bytes = await file.read()
        result = svc.import_owl(base_id, scene_id, zip_bytes)
        return ok(data=result, message="imported")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Application services
# ══════════════════════════════════════════════════


@router.post("/{owner_type}/{base_id}/instances/search")
def search_instances(owner_type: str, base_id: str, body: dict):
    """Search instances in a base."""
    svc = get_service()
    try:
        return ok(data=svc.search_instances(base_id, body))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/graph/query")
def graph_query(owner_type: str, base_id: str, scene_id: str, body: dict):
    """Query the graph of objects and relations."""
    svc = get_service()
    try:
        return ok(data=svc.graph_query(base_id, scene_id, body))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{owner_type}/{base_id}/scenes/{scene_id}/graph/path")
def graph_path(owner_type: str, base_id: str, scene_id: str, body: dict):
    """Find shortest path between two objects."""
    svc = get_service()
    try:
        return ok(data=svc.graph_path(base_id, scene_id, body))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
