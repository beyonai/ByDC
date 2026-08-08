"""RPC handlers for ontology_doc_fragment service.

Methods:
  - batchCreate: batch-create fragments (instance_id, origin_instance_id, content)
  - listByInstanceIds: paginated query by instance_id list
  - updateStatus: bulk status update by primary-key id list
  - buildObjectInstance: submit object instance build work in the background

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
_BEYOND_TOKEN_HEADER = "beyond-token"


def _user_code(req: Request) -> str:
    """Extract operator identifier from X-User-Code header."""
    return req.headers.get(_USER_CODE_HEADER, "")


def _beyond_token(req: Request) -> str:
    """Extract Beyond-Token header required by downstream UserFS writes."""
    return req.headers.get(_BEYOND_TOKEN_HEADER, "").strip()


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
    """Accept object instance build work and run it after the response."""
    raw_ids = params.get("instance_ids", [])
    if not isinstance(raw_ids, list):
        raise ValueError("instance_ids must be a list")
    instance_ids = [str(item) for item in raw_ids]

    operator = _user_code(req)
    if not operator:
        raise ValueError(f"Request header '{_USER_CODE_HEADER}' is required")
    beyond_token = _beyond_token(req)
    if not beyond_token:
        raise ValueError(f"Request header '{_BEYOND_TOKEN_HEADER}' is required")

    service = get_object_instance_build_task_service(platform)
    accepted, run_request = service.accept(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=instance_ids,
            batch_size=int(params.get("batch_size", 20)),
            operator=operator,
            beyond_token=beyond_token,
        )
    )
    background_tasks = getattr(req.state, "background_tasks", None)
    if background_tasks is None:
        await service.run(run_request)
    else:
        background_tasks.add_task(service.run, run_request)
    return ok(data=accepted.to_dict(), message="accepted")


def _get_object_instance_build_task(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Task table status query is no longer supported.

    显式返回 501（废弃接口语义保留），不依赖 _EXCEPTION_MAP 的
    NotImplementedError → 501 隐式映射（该映射已随锚定/抽取落地移除）。
    """
    return ok(
        code=501,
        message=(
            "getObjectInstanceBuildTask is no longer supported; "
            "check ontology_doc_fragment.status and service logs instead"
        ),
        data=None,
    )


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, Any] = {
    "batchCreate": _batch_create,
    "listByInstanceIds": _list_by_instance_ids,
    "updateStatus": _update_status,
    "buildObjectInstance": _build_object_instance,
    "getObjectInstanceBuildTask": _get_object_instance_build_task,
}
