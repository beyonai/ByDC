"""RPC handlers for 'action' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.action import Action
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok
from datacloud_platform.services.object_action import get_object_action_schema

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_actions(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    result = platform.get_actions(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_code=params.get("object_code", ""),
        owner_type=params.get("owner_type"),
        user_code=params.get("user_code"),
        keyword=params.get("keyword"),
    )
    items = result[0] if isinstance(result, tuple) else result
    return ok(data=items)


def _get_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    object_code: str = params.get("object_code", "")
    code: str = params.get("code", "")
    action = platform.get_action_detail(
        params.get("base_id", DEFAULT_BASE_ID),
        object_code,
        code,
    )
    if action is None:
        raise KeyError(f"Action '{code}' not found")
    return ok(data=action)


def _get_action_schema(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    object_code = str(params.get("object_code") or "").strip()
    action_code = str(params.get("code") or params.get("action_code") or "").strip()
    if not object_code:
        raise ValueError("object_code is required")
    if not action_code:
        raise ValueError("code/action_code is required")
    schema = get_object_action_schema(
        platform=platform,
        base_id=str(params.get("base_id") or DEFAULT_BASE_ID),
        object_code=object_code,
        action_code=action_code,
    )
    return ok(data=schema)


def _create_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_action(
            params.get("base_id", DEFAULT_BASE_ID),
            params.get("object_code", ""),
            Action(**(params.get("action") or {})),
        ),
        message="created",
    )


def _update_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    object_code: str = params.get("object_code", "")
    code: str = params.get("code", "")
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
        params.get("object_code", ""),
        params.get("code", ""),
    )
    return ok(message="deleted")


REGISTRY: dict[str, Any] = {
    "listActions": _list_actions,
    "getAction": _get_action,
    "getActionSchema": _get_action_schema,
    "createAction": _create_action,
    "updateAction": _update_action,
    "deleteAction": _delete_action,
}
