"""RPC handlers for 'action' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.action import Action
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_actions(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_actions(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            object_code=params["object_code"],
            owner_type=params.get("owner_type"),
            user_code=params.get("user_code"),
            keyword=params.get("keyword"),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


def _get_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    object_code: str = params["object_code"]
    code: str = params["code"]
    action = platform.get_action_detail(
        params.get("base_id", DEFAULT_BASE_ID),
        object_code,
        code,
        cache_mode=params.get("cache_mode", CacheMode.REALTIME),
    )
    if action is None:
        raise KeyError(f"Action '{code}' not found")
    return ok(data=action)


def _create_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_action(
            params.get("base_id", DEFAULT_BASE_ID),
            params["object_code"],
            Action(**(params.get("action") or {})),
        ),
        message="created",
    )


def _update_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    object_code: str = params["object_code"]
    code: str = params["code"]
    platform.update_action(
        params.get("base_id", DEFAULT_BASE_ID),
        object_code,
        code,
        Action(**(params.get("action") or {})),
    )
    return ok(data={"actionCode": code})


def _delete_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_action(
        params.get("base_id", DEFAULT_BASE_ID),
        params["object_code"],
        params["code"],
    )
    return ok(message="deleted")


REGISTRY: dict[str, Any] = {
    "listActions": _list_actions,
    "getAction": _get_action,
    "createAction": _create_action,
    "updateAction": _update_action,
    "deleteAction": _delete_action,
}
