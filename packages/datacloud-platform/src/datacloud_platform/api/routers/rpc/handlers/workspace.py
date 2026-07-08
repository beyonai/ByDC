"""RPC handlers for 'workspace' service.

Note: workspace_routes.py is not currently mounted in server.py (only
ontology_build_routes.py is).  These handlers are ready for when workspace
routes are activated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _workspace_init(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.workspace_init(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        workspace_desc=params.get("workspace_desc", ""),
    )


def _workspace_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.workspace_list(user_code=params.get("user_code", ""))


def _workspace_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.workspace_get(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
    )


def _workspace_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.workspace_delete(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
    )


def _workspace_batch_submit(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.workspace_batch_submit(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        only=params.get("only") or None,
        confirm_drop_columns=params.get("confirm_drop_columns", False),
    )


def _collect_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    ws_name = params.get("workspace_name", "")
    if ws_name:
        return platform.collect_object_to_workspace(
            user_code=params.get("user_code", ""),
            workspace_name=ws_name,
            entity_code=params["entity_code"],
            entity_name=params.get("entity_name", ""),
            entity_desc=params.get("entity_desc", ""),
            fields=params.get("fields"),
            term_sync=params.get("term_sync"),
        )
    return platform.collect_object_info(
        user_code=params.get("user_code", ""),
        entity_code=params["entity_code"],
        entity_name=params.get("entity_name", ""),
        entity_desc=params.get("entity_desc", ""),
        fields=params.get("fields"),
    )


def _delete_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    ws_name = params.get("workspace_name", "")
    if ws_name:
        return platform.delete_workspace_object(
            user_code=params.get("user_code", ""),
            workspace_name=ws_name,
            entity_code=params["entity_code"],
        )
    return platform.delete_build_object(
        user_code=params.get("user_code", ""),
        entity_code=params["entity_code"],
    )


def _list_objects(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.list_workspace_objects(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
    )


def _get_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.get_workspace_object(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
    )


def _get_object_fields(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.get_workspace_object_fields(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
    )


def _collect_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    ws_name = params.get("workspace_name", "")
    if ws_name:
        return platform.collect_view_to_workspace(
            user_code=params.get("user_code", ""),
            workspace_name=ws_name,
            view_code=params["view_code"],
            view_name=params.get("view_name", ""),
            view_desc=params.get("view_desc", ""),
            object_codes=params.get("object_codes"),
            object_relations=params.get("object_relations"),
            fields=params.get("fields"),
        )
    return platform.collect_view_info(
        user_code=params.get("user_code", ""),
        view_code=params["view_code"],
        view_name=params.get("view_name", ""),
        view_desc=params.get("view_desc", ""),
        object_codes=params.get("object_codes"),
        object_relations=params.get("object_relations"),
        fields=params.get("fields"),
    )


def _delete_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    ws_name = params.get("workspace_name", "")
    if ws_name:
        return platform.delete_workspace_view(
            user_code=params.get("user_code", ""),
            workspace_name=ws_name,
            view_code=params["view_code"],
        )
    return platform.delete_build_view(
        user_code=params.get("user_code", ""),
        view_code=params["view_code"],
    )


def _list_views(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.list_workspace_views(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
    )


def _get_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.get_workspace_view(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        view_code=params["view_code"],
    )


def _collect_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.collect_action(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
        action_code=params["action_code"],
        action_name=params["action_name"],
        script=params["script"],
        params=params.get("action_params") or [],
        action_desc=params.get("action_desc", ""),
        action_type=params.get("action_type", "OPERATION"),
        permission_roles=params.get("permission_roles"),
        object_references=params.get("object_references"),
    )


def _delete_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.delete_workspace_action(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
        action_code=params["action_code"],
    )


async def _run_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return await platform.run_action_debug(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
        action_code=params["action_code"],
        params=params.get("action_params") or {},
    )


def _list_actions(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.list_workspace_actions(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
    )


def _get_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.get_workspace_action(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
        action_code=params["action_code"],
    )


def _get_sdk(platform: DatacloudPlatform, params: dict[str, Any], _req: Request) -> Any:
    return platform.get_workspace_sdk(
        user_code=params.get("user_code", ""),
        workspace_name=params["workspace_name"],
        entity_code=params["entity_code"],
    )


REGISTRY: dict[str, Any] = {
    "init": _workspace_init,
    "list": _workspace_list,
    "get": _workspace_get,
    "delete": _workspace_delete,
    "batchSubmit": _workspace_batch_submit,
    "collectObject": _collect_object,
    "deleteObject": _delete_object,
    "listObjects": _list_objects,
    "getObject": _get_object,
    "getObjectFields": _get_object_fields,
    "collectView": _collect_view,
    "deleteView": _delete_view,
    "listViews": _list_views,
    "getView": _get_view,
    "collectAction": _collect_action,
    "deleteAction": _delete_action,
    "runAction": _run_action,
    "listActions": _list_actions,
    "getAction": _get_action,
    "getSdk": _get_sdk,
}
