"""RPC handlers for 'relation' service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.relation import Relation
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _list_relations(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.get_relations(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            owner_type=params.get("owner_type"),
            user_code=params.get("user_code"),
            keyword=params.get("keyword"),
            cache_mode=params.get("cache_mode", CacheMode.REALTIME),
        )
    )


def _get_relation(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    rel = platform.get_relation_detail(
        params.get("base_id", DEFAULT_BASE_ID),
        code,
        cache_mode=params.get("cache_mode", CacheMode.REALTIME),
    )
    if rel is None:
        raise KeyError(f"Relation '{code}' not found")
    return ok(data=rel)


def _create_relation(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_relation(
            params.get("base_id", DEFAULT_BASE_ID),
            Relation(**(params.get("relation") or {})),
        ),
        message="created",
    )


def _update_relation(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    platform.update_relation(
        params.get("base_id", DEFAULT_BASE_ID),
        code,
        Relation(**(params.get("relation") or {})),
    )
    return ok(data={"relationCode": code})


def _delete_relation(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_relation(params.get("base_id", DEFAULT_BASE_ID), params["code"])
    return ok(message="deleted")


REGISTRY: dict[str, Any] = {
    "listRelations": _list_relations,
    "getRelation": _get_relation,
    "createRelation": _create_relation,
    "updateRelation": _update_relation,
    "deleteRelation": _delete_relation,
}
