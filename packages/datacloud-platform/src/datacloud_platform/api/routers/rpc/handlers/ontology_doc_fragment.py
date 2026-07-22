"""RPC handlers for ontology_doc_fragment service.

Methods:
  - batchCreate: batch-create fragments (instance_id, origin_instance_id, content)
  - listByInstanceIds: paginated query by instance_id list
  - updateStatus: bulk status update by primary-key id list
  - buildObjectInstance: submit an object instance build task
  - getObjectInstanceBuildTask: query object instance build task status

User identity is read from the ``X-User-Code`` request header.
base_id always uses the global DEFAULT_BASE_ID — callers must not pass it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok
from datacloud_platform.services.object_instance_build_task_service import (
    SubmitObjectInstanceBuildTaskRequest,
    get_object_instance_build_task_service,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)

_USER_CODE_HEADER = "X-User-Code"


def _user_code(req: Request) -> str:
    """Extract operator identifier from X-User-Code header."""
    return req.headers.get(_USER_CODE_HEADER, "")


# ── batchCreate ───────────────────────────────────────────────────────────────


def _batch_create(
    platform: DatacloudPlatform, params: dict[str, Any], req: Request
) -> Any:
    """Batch-create doc fragments.

    Params:
      - items: list of {instanceId/instance_id, originInstanceId/origin_instance_id?, content}

    Header:
      - X-User-Code: operator identifier (required)
    """
    raw_items: list[dict[str, Any]] = params.get("items") or []
    if not raw_items:
        raise ValueError("items is required and must be a non-empty list")

    created_by = _user_code(req)
    if not created_by:
        raise ValueError(f"Request header '{_USER_CODE_HEADER}' is required")

    items: list[dict[str, Any]] = [
        {
            "instance_id": str(item.get("instance_id") or item.get("instanceId") or ""),
            "origin_instance_id": item.get("origin_instance_id")
            or item.get("originInstanceId")
            or None,
            "content": str(item.get("content") or ""),
        }
        for item in raw_items
    ]

    ids = platform.batch_create_fragments(
        DEFAULT_BASE_ID, items=items, created_by=created_by
    )
    return ok(data=ids, message="created")


# ── listByInstanceIds ─────────────────────────────────────────────────────────


def _list_by_instance_ids(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Paginated query by instance_id list.

    Params:
      - instanceIds / instance_ids: list[str] (required)
      - page_index: int (default 1)
      - page_size: int (default 20)
    """
    raw_ids: list[str] | None = params.get("instance_ids") or params.get("instanceIds")
    if not raw_ids:
        raise ValueError("instance_ids / instanceIds is required")

    instance_ids = [str(i) for i in raw_ids if i]
    page_index: int = int(params.get("page_index", 1))
    page_size: int = int(params.get("page_size", 20))

    status: int | None = None
    if params.get("status") is not None:
        status = int(params["status"])
        if status not in (0, 1):
            raise ValueError("status must be 0 (未融合) or 1 (已融合)")

    result = platform.list_fragments_by_instance_ids(
        DEFAULT_BASE_ID,
        instance_ids=instance_ids,
        page_index=page_index,
        page_size=page_size,
        status=status,
    )
    return ok(data=result)


# ── updateStatus ──────────────────────────────────────────────────────────────


def _update_status(
    platform: DatacloudPlatform, params: dict[str, Any], req: Request
) -> Any:
    """Bulk status update by primary-key id list.

    Params:
      - ids: list[int] (required)
      - status: int — 0=未融合, 1=已融合 (required)

    Header:
      - X-User-Code: operator identifier (required)
    """
    raw_ids: list[Any] | None = params.get("ids")
    if not raw_ids:
        raise ValueError("ids is required and must be a non-empty list")

    ids: list[int] = [int(i) for i in raw_ids]

    status_raw = params.get("status")
    if status_raw is None:
        raise ValueError("status is required")
    status: int = int(status_raw)
    if status not in (0, 1):
        raise ValueError("status must be 0 (未融合) or 1 (已融合)")

    updated_by = _user_code(req)
    if not updated_by:
        raise ValueError(f"Request header '{_USER_CODE_HEADER}' is required")

    updated = platform.update_fragment_status_by_ids(
        DEFAULT_BASE_ID, ids=ids, status=status, updated_by=updated_by
    )
    return ok(data={"updated": updated})


async def _build_object_instance(
    platform: DatacloudPlatform, params: dict[str, Any], req: Request
) -> Any:
    """Submit an asynchronous object instance build task."""
    raw_ids = params.get("instance_ids", [])
    if not isinstance(raw_ids, list):
        raise ValueError("instance_ids must be a list")
    instance_ids = [str(item) for item in raw_ids]

    operator = _user_code(req)
    if not operator:
        raise ValueError(f"Request header '{_USER_CODE_HEADER}' is required")

    service = get_object_instance_build_task_service(platform)
    task = await service.submit(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=instance_ids,
            batch_size=int(params.get("batch_size", 20)),
            operator=operator,
        )
    )
    return ok(data=task.to_dict(), message="accepted")


def _get_object_instance_build_task(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Query an object instance build task by task_id."""
    task_id = str(params.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")

    service = get_object_instance_build_task_service(platform)
    return ok(data=service.get_task(task_id).to_dict())


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, Any] = {
    "batchCreate": _batch_create,
    "listByInstanceIds": _list_by_instance_ids,
    "updateStatus": _update_status,
    "buildObjectInstance": _build_object_instance,
    "getObjectInstanceBuildTask": _get_object_instance_build_task,
}
