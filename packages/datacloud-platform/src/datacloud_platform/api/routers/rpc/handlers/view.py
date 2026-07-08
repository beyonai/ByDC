"""RPC handlers for 'view' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.models.view import View
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _parse_csv(param: str | None) -> list[str] | None:
    if param is None or not param.strip():
        return None
    return [v.strip() for v in param.split(",") if v.strip()]


def _list_views(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_views(
            base_id=params.get("base_id", "default"),
            owner_type=params.get("owner_type"),
            user_code=params.get("user_code"),
            keyword=params.get("keyword"),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


def _get_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    view = platform.get_view_detail(
        params.get("base_id", "default"),
        code,
        cache_mode=params.get("cache_mode", CacheMode.REALTIME),
    )
    if view is None:
        raise KeyError(f"View '{code}' not found")
    return ok(data=view)


def _create_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_view_with_scene(
            params.get("base_id", "default"),
            View(**(params.get("view") or {})),
        ),
        message="created",
    )


def _update_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    platform.update_view(
        params.get("base_id", "default"),
        code,
        View(**(params.get("view") or {})),
    )
    return ok(data={"viewCode": code})


def _delete_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_view_from_all_scenes(
        params.get("base_id", "default"), params["code"]
    )
    return ok(message="deleted")


def _get_term_bindings(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_view_property_term_bindings(
            params.get("base_id", "default"),
            params["view_code"],
            term_master_type=params.get("term_master_type"),
            property_codes=_parse_csv(params.get("property_codes")),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


def _get_objects(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_objects_by_view(
            params.get("base_id", "default"),
            params["view_code"],
            owner_type=params.get("owner_type"),
            user_code=params.get("user_code"),
            keyword=params.get("keyword"),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


REGISTRY: dict[str, Any] = {
    "listViews": _list_views,
    "getView": _get_view,
    "createView": _create_view,
    "updateView": _update_view,
    "deleteView": _delete_view,
    "getTermBindings": _get_term_bindings,
    "getObjects": _get_objects,
}
