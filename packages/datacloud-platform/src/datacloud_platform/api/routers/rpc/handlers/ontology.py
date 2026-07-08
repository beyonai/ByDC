"""RPC handlers for 'ontology' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_bases(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(data=platform.list_bases(keyword=params.get("keyword")))


def _create_base(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    from datacloud_platform.base_entry import (
        OntologyBaseEntry,
        generate_snowflake,
        validate_base_id,
    )

    base_id = params.get("base_id")
    if base_id:
        if not validate_base_id(base_id):
            raise ValueError(f"Invalid baseId '{base_id}'")  # noqa: TRY004
        if platform.base_exists(base_id):
            raise ValueError(f"OntologyBase '{base_id}' already exists")  # noqa: TRY004
    else:
        base_id = generate_snowflake()

    source_url = params.get("source_url")
    entry = OntologyBaseEntry(
        base_id=base_id,
        display_name=params.get("display_name", ""),
        description=params.get("description", ""),
        source_type="REMOTE" if source_url else "LOCAL",
        source_url=source_url,
        auth_type=params.get("auth_type"),
        auth_config=params.get("auth_config"),
        timeout_sec=params.get("timeout_sec", 300),
    )
    return ok(data=platform.create_base(entry), message="created")


def _delete_base(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_base(params["base_id"])  # KeyError → 404
    return ok(message="deleted")


def _update_base(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    from datacloud_platform.models.base_entry import OntologyBaseUpdate

    result = platform.update_base(
        params["base_id"],  # KeyError → 404
        OntologyBaseUpdate(**(params.get("updates") or {})),
    )
    return ok(data=result, message="updated")


def _get_base_detail(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    base_id = params.get("base_id", DEFAULT_BASE_ID)
    loader = platform._load_ontology_cached(base_id)
    backend = platform._ontology_for(base_id)
    result = backend.get_base_details(
        loader,
        base_id,
        view_code=params.get("view_code"),
        object_code=params.get("object_code"),
    )
    return ok(data=result)


def _resync(platform: DatacloudPlatform, params: dict[str, Any], _req: Request) -> Any:
    sync = getattr(platform, "_sync_adapter", None)
    if sync is None:
        raise NotImplementedError("Sync adapter not configured")
    return ok(
        data={
            "message": "Resync started",
            "base_id": params.get("base_id", DEFAULT_BASE_ID),
        }
    )


REGISTRY: dict[str, Any] = {
    "listBases": _list_bases,
    "createBase": _create_base,
    "deleteBase": _delete_base,
    "updateBase": _update_base,
    "getBaseDetail": _get_base_detail,
    "resync": _resync,
}
