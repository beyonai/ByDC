"""RPC handlers for 'datasource' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.models.datasource import Datasource
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_datasources(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_datasources(
            base_id=params.get("base_id", "default"),
            keyword=params.get("keyword"),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


def _get_datasource(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    db_id: str = params["db_id"]
    ds = platform.get_datasource_detail(
        params.get("base_id", "default"),
        db_id,
        cache_mode=params.get("cache_mode", CacheMode.REALTIME),
    )
    if ds is None:
        raise KeyError(f"Datasource '{db_id}' not found")
    return ok(data=ds)


def _create_datasource(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_datasource(
            params.get("base_id", "default"),
            Datasource(**(params.get("datasource") or {})),
        ),
        message="created",
    )


def _delete_datasource(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_datasource(params.get("base_id", "default"), params["db_id"])
    return ok(message="deleted")


REGISTRY: dict[str, Any] = {
    "listDatasources": _list_datasources,
    "getDatasource": _get_datasource,
    "createDatasource": _create_datasource,
    "deleteDatasource": _delete_datasource,
}
