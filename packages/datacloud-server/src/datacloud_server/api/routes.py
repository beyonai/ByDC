"""Ontology service REST API routes.

All responses: {code:200, success:true, message:"ok", data:...}
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from datacloud_server.api.deps import get_service

router = APIRouter(prefix="/api/v1/ontologyBases", tags=["ontology"])


def _ok(data: object = None, message: str = "ok") -> dict:
    return {"code": 200, "success": True, "message": message, "data": data}


# ══════════════════════════════════════════════════
# OntologyBase management
# ══════════════════════════════════════════════════


@router.get("")
def list_bases():
    """List all ontology bases."""
    svc = get_service()
    return _ok(data=svc.list_bases())


@router.post("")
def create_base(body: dict):
    """Create an ontology base.

    sourceType is auto-derived: sourceUrl present -> REMOTE, else LOCAL.
    """
    svc = get_service()
    try:
        return _ok(data=svc.create_base(body), message="created")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{base_id}")
def delete_base(base_id: str):
    """Delete an ontology base."""
    svc = get_service()
    try:
        svc.delete_base(base_id)
        return _ok(message="deleted")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Scene management
# ══════════════════════════════════════════════════


@router.get("/{base_id}/scenes")
def list_scenes(base_id: str):
    """List scenes under an ontology base."""
    svc = get_service()
    try:
        return _ok(data=svc.list_scenes(base_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# View CRUD
# ══════════════════════════════════════════════════


@router.get("/{base_id}/scenes/{scene_id}/views")
def list_views(base_id: str, scene_id: str):
    """List views in a scene."""
    svc = get_service()
    try:
        return _ok(data=svc.get_views(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{base_id}/scenes/{scene_id}/views/{code}")
def get_view(base_id: str, scene_id: str, code: str):
    """Get view detail."""
    svc = get_service()
    try:
        view = svc.get_view_detail(base_id, scene_id, code)
        if view is None:
            raise HTTPException(status_code=404, detail=f"View '{code}' not found")
        return _ok(data=view)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{base_id}/scenes/{scene_id}/views")
def create_view(base_id: str, scene_id: str, body: dict):
    """Create a view (LOCAL only)."""
    svc = get_service()
    try:
        return _ok(data=svc.create_view(base_id, scene_id, body), message="created")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{base_id}/scenes/{scene_id}/views/{code}")
def delete_view(base_id: str, scene_id: str, code: str):
    """Delete a view (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_view(base_id, scene_id, code)
        return _ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Relation CRUD
# ══════════════════════════════════════════════════


@router.get("/{base_id}/scenes/{scene_id}/relations")
def list_relations(base_id: str, scene_id: str):
    """List relations in a scene."""
    svc = get_service()
    try:
        return _ok(data=svc.get_relations(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{base_id}/scenes/{scene_id}/relations/{code}")
def get_relation(base_id: str, scene_id: str, code: str):
    """Get relation detail."""
    svc = get_service()
    try:
        rel = svc.get_relation_detail(base_id, scene_id, code)
        if rel is None:
            raise HTTPException(status_code=404, detail=f"Relation '{code}' not found")
        return _ok(data=rel)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{base_id}/scenes/{scene_id}/relations")
def create_relation(base_id: str, scene_id: str, body: dict):
    """Create a relation (LOCAL only)."""
    svc = get_service()
    try:
        return _ok(data=svc.create_relation(base_id, scene_id, body), message="created")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{base_id}/scenes/{scene_id}/relations/{code}")
def delete_relation(base_id: str, scene_id: str, code: str):
    """Delete a relation (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_relation(base_id, scene_id, code)
        return _ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Datasource CRUD
# ══════════════════════════════════════════════════


@router.get("/{base_id}/scenes/{scene_id}/datasources")
def list_datasources(base_id: str, scene_id: str):
    """List datasources in a scene."""
    svc = get_service()
    try:
        return _ok(data=svc.get_datasources(base_id, scene_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{base_id}/scenes/{scene_id}/datasources/{db_id}")
def get_datasource(base_id: str, scene_id: str, db_id: str):
    """Get datasource detail."""
    svc = get_service()
    try:
        ds = svc.get_datasource_detail(base_id, scene_id, db_id)
        if ds is None:
            raise HTTPException(status_code=404, detail=f"Datasource '{db_id}' not found")
        return _ok(data=ds)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{base_id}/scenes/{scene_id}/datasources")
def create_datasource(base_id: str, scene_id: str, body: dict):
    """Create a datasource (LOCAL only)."""
    svc = get_service()
    try:
        return _ok(data=svc.create_datasource(base_id, scene_id, body), message="created")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{base_id}/scenes/{scene_id}/datasources/{db_id}")
def delete_datasource(base_id: str, scene_id: str, db_id: str):
    """Delete a datasource (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_datasource(base_id, scene_id, db_id)
        return _ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# Object CRUD
# ══════════════════════════════════════════════════


@router.get("/{base_id}/scenes/{scene_id}/objects")
def list_objects(base_id: str, scene_id: str, cache: bool = False):
    """List objects in a scene."""
    svc = get_service()
    try:
        return _ok(data=svc.get_objects(base_id, scene_id, use_cache=cache))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{base_id}/scenes/{scene_id}/objects/{code}")
def get_object(base_id: str, scene_id: str, code: str):
    """Get object detail."""
    svc = get_service()
    try:
        obj = svc.get_object_detail(base_id, scene_id, code)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"Object '{code}' not found")
        return _ok(data=obj)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{base_id}/scenes/{scene_id}/objects")
def create_object(base_id: str, scene_id: str, body: dict):
    """Create an object (LOCAL only)."""
    svc = get_service()
    try:
        return _ok(data=svc.create_object(base_id, scene_id, body), message="created")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{base_id}/scenes/{scene_id}/objects/{code}")
def delete_object(base_id: str, scene_id: str, code: str):
    """Delete an object (LOCAL only)."""
    svc = get_service()
    try:
        svc.delete_object(base_id, scene_id, code)
        return _ok(message="deleted")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ══════════════════════════════════════════════════
# OWL import
# ══════════════════════════════════════════════════


@router.post("/{base_id}/scenes/{scene_id}/import-owl")
async def import_owl(
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
        return _ok(data=result, message="imported")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
