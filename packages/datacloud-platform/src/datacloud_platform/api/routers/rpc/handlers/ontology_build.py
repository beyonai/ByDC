"""RPC handlers for 'ontologyBuild' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _collect_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.collect_object_info(
        user_code=params.get("user_code", ""),
        entity_code=params.get("entity_code", ""),
        session_id=params.get("session_id", ""),
        entity_name=params.get("entity_name", ""),
        entity_desc=params.get("entity_desc", ""),
        fields=params.get("fields"),
        kb_id=params.get("kb_id", ""),
        kb_directory=params.get("kb_directory", ""),
        base_id=params.get("base_id", ""),
        ext_property=params.get("ext_property", {}),
    )


def _submit_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.submit_object(
        user_code=params.get("user_code", ""),
        entity_code=params.get("entity_code", ""),
        session_id=params.get("session_id", ""),
        base_id=params.get("base_id", ""),
    )


def _delete_object(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.delete_build_object(
        user_code=params.get("user_code", ""),
        entity_code=params.get("entity_code", ""),
        base_id=params.get("base_id", ""),
    )


def _collect_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.collect_view_info(
        user_code=params.get("user_code", ""),
        view_code=params.get("view_code", ""),
        session_id=params.get("session_id", ""),
        view_name=params.get("view_name", ""),
        view_desc=params.get("view_desc", ""),
        object_codes=params.get("object_codes"),
        object_relations=params.get("object_relations"),
        fields=params.get("fields"),
        base_id=params.get("base_id", ""),
    )


def _submit_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.submit_view(
        user_code=params.get("user_code", ""),
        view_code=params.get("view_code", ""),
        session_id=params.get("session_id", ""),
        base_id=params.get("base_id", ""),
    )


def _delete_view(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.delete_build_view(
        user_code=params.get("user_code", ""),
        view_code=params.get("view_code", ""),
        base_id=params.get("base_id", ""),
    )


def _list_term_types(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.list_bindable_term_types(
        keyword=params.get("keyword", ""),
        base_id=params.get("base_id", ""),
    )


def _get_term_type_values(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return platform.get_term_type_values(
        term_type_code=params.get("term_type_code", ""),
        keyword=params.get("keyword", ""),
        base_id=params.get("base_id", ""),
    )


REGISTRY: dict[str, Any] = {
    "collectObject": _collect_object,
    "submitObject": _submit_object,
    "deleteObject": _delete_object,
    "collectView": _collect_view,
    "submitView": _submit_view,
    "deleteView": _delete_view,
    "listTermTypes": _list_term_types,
    "getTermTypeValues": _get_term_type_values,
}
