"""Ontology service REST API routes.

All responses: {code:200, success:true, message:"ok", data:...}
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

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
