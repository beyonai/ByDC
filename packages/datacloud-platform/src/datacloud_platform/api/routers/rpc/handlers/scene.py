"""RPC handlers for 'scene' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.scene import (
    SceneCreate,
    SceneMembersRequest,
    SceneUpdate,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_scenes(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    keyword = params.get("keyword")
    if keyword:
        return ok(
            data=platform.query_scenes(base_id, keyword),
            totalCount=platform.count_scenes(base_id, keyword),
        )
    return ok(data=platform.list_scenes(base_id))


def _create_scene(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    result = platform.create_scene(base_id, SceneCreate(**(params.get("scene") or {})))
    return ok(data=result, message="created")


def _get_scene(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    result = platform.get_scene_details(
        base_id,
        params["scene_id"],  # KeyError → 404
        view_code=params.get("view_code"),
        object_code=params.get("object_code"),
    )
    return ok(data=result)


def _update_scene(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    result = platform.update_scene(
        base_id, params["scene_id"], SceneUpdate(**(params.get("updates") or {}))
    )
    return ok(data=result, message="updated")


def _delete_scene(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_scene_with_migration(
        params.get("base_id", DEFAULT_BASE_ID), params["scene_id"]
    )
    return ok(message="deleted")


def _add_members(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    scene_id: str = params["scene_id"]
    member = SceneMembersRequest(
        objectCodes=params.get("object_codes", []),
        viewCodes=params.get("view_codes", []),
    )
    result = platform.add_scene_members(
        base_id, scene_id, member.object_codes, member.view_codes
    )
    return ok(data=result, message="members added")


def _remove_members(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    scene_id: str = params["scene_id"]
    for obj_code in params.get("object_codes", []):
        platform.remove_object_from_scene_safe(base_id, scene_id, obj_code)
    for vw_code in params.get("view_codes", []):
        platform.remove_view_from_scene_safe(base_id, scene_id, vw_code)
    return ok(message="members removed")


def _query_ontologies(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    result = platform.query_ontologies_by_scene(
        base_id,
        params["scene_id"],
        page=params.get("page", 1),
        page_size=params.get("page_size", 20),
        keyword=params.get("keyword"),
    )
    return ok(data=result["data"], totalCount=result["totalCount"])


def _query_ontologies_by_code(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    scene_code: str = params["scene_code"]
    cross_scene = scene_code == "-1"

    backend = platform._ontology_for(base_id)
    scene_id = ""
    if not cross_scene:
        scenes = backend.list_scenes(base_id)
        for s in scenes:
            if s.get("scene_code") == scene_code:
                scene_id = s.get("scene_id", "")
                break
        if not scene_id:
            return ok(data={"objects": [], "views": []}, totalCount=0)

    loader = platform._load_ontology_cached(base_id)
    result = backend.query_ontologies_by_scene(
        loader=loader,
        base_id=base_id,
        scene_id=scene_id,
        page=params.get("page", 1),
        page_size=params.get("page_size", 20),
        keyword=params.get("keyword"),
        type=params.get("ont_type"),
        owner_type=params.get("owner_type"),
        user_code=params.get("user_code"),
        cross_scene=cross_scene,
    )
    return ok(data=result["data"], totalCount=result["totalCount"])


REGISTRY: dict[str, Any] = {
    "listScenes": _list_scenes,
    "createScene": _create_scene,
    "getScene": _get_scene,
    "updateScene": _update_scene,
    "deleteScene": _delete_scene,
    "addMembers": _add_members,
    "removeMembers": _remove_members,
    "queryOntologies": _query_ontologies,
    "queryOntologiesByCode": _query_ontologies_by_code,
}
