"""RPC handlers for 'objectType' service.

NOTE: Named ``object_type.py`` to avoid shadowing Python builtin ``object``.
The URL path uses ``objectType`` (camelCase).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.object_type import ObjectType

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _parse_csv(param: str | None) -> list[str] | None:
    if param is None or not param.strip():
        return None
    return [v.strip() for v in param.split(",") if v.strip()]


def _list_objects(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    items, _ = platform.get_objects(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        owner_type=params.get("owner_type"),
        user_code=params.get("user_code"),
        keyword=params.get("keyword"),
    )
    return ok(data=items)


def _get_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]  # KeyError → 404
    obj = platform.get_object_detail(
        params.get("base_id", DEFAULT_BASE_ID),
        code,
    )
    if obj is None:
        raise KeyError(f"Object '{code}' not found")
    return ok(data=obj)


def _create_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_object_with_scene(
            params.get("base_id", DEFAULT_BASE_ID),
            ObjectType(**(params.get("object") or {})),
        ),
        message="created",
    )


def _update_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    platform.update_object(
        params.get("base_id", DEFAULT_BASE_ID),
        code,
        ObjectType(**(params.get("object") or {})),
    )
    return ok(data={"objectCode": code})


def _delete_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_object_from_all_scenes(
        params.get("base_id", DEFAULT_BASE_ID), params["code"]
    )
    return ok(message="deleted")


def _get_subtree(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    code: str = params["object_code"]
    result = platform.get_object_subtree(base_id, code)
    if result["object"] is None:
        raise KeyError(f"Object '{code}' not found")
    return ok(data=result)


def _get_term_bindings(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_object_property_term_bindings(
            params.get("base_id", DEFAULT_BASE_ID),
            params["object_code"],
            term_master_type=params.get("term_master_type"),
            property_codes=_parse_csv(params.get("property_codes")),
        )
    )


def _get_relations(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_relations_by_object(
            params.get("base_id", DEFAULT_BASE_ID),
            params["object_code"],
            owner_type=params.get("owner_type"),
            user_code=params.get("user_code"),
        )
    )


REGISTRY: dict[str, Any] = {
    "listObjects": _list_objects,
    "getObject": _get_object,
    "createObject": _create_object,
    "updateObject": _update_object,
    "deleteObject": _delete_object,
    "getSubtree": _get_subtree,
    "getTermBindings": _get_term_bindings,
    "getRelations": _get_relations,
}
