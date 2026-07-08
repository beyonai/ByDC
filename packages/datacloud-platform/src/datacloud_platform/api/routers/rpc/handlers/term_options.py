"""RPC handler for 'termOptions' service.

NOTE: This delegates to the same loader_runtime mechanism as the existing
POST /api/v1/datacloud/terms/options endpoint.  The RPC handler has access
to ``request: Request`` via the handler signature, so it can call
``get_request_loader_snapshot(request)`` directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.loader_runtime import get_request_loader_snapshot
from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


async def _term_options_query(
    platform: DatacloudPlatform, params: dict[str, Any], request: Request
) -> Any:
    term_set = str(params.get("termSet", "")).strip()
    term_type_code = str(params.get("termTypeCode", "")).strip()
    if not term_set:
        raise ValueError("termSet is required")
    if not term_type_code:
        raise ValueError("termTypeCode is required")

    page = max(int(params.get("page", 1)), 1)
    page_size = min(max(int(params.get("pageSize", 20)), 1), 100)
    term_field = str(params.get("termField", "")).strip().lower()
    keyword = str(params.get("keyword", "")).strip()
    dataset_id = params.get("datasetId")
    offset = (page - 1) * page_size

    snapshot = await get_request_loader_snapshot(request, reason="term_options")
    term_loader = (
        getattr(getattr(snapshot.loader, "_config", None), "term_loader", None)
        if snapshot is not None
        else None
    )
    if term_loader is None:
        logger.warning("term options requested but term_loader is not configured")
        return ok(
            data={
                "items": [],
                "page": page,
                "pageSize": page_size,
                "total": 0,
                "hasMore": False,
            }
        )

    try:
        raw_entries, total = term_loader.get_entries_page(
            term_set,
            dataset_id=dataset_id,
            term_type_code=term_type_code,
            keyword=keyword,
            limit=page_size,
            offset=offset,
        )
        raw_entries = list(raw_entries or [])
    except AttributeError:
        all_entries = list(
            term_loader.get_entries(
                term_set,
                dataset_id=dataset_id,
                term_type_code=term_type_code,
                keyword=keyword,
            )
            or []
        )
        total = len(all_entries)
        raw_entries = all_entries[offset : offset + page_size]

    items = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or entry.get("value") or "").strip()
        name = str(entry.get("name") or entry.get("label") or "").strip()
        label = str(entry.get("label") or name or code).strip()
        value = name if term_field == "name" else code
        if not value:
            value = label
        items.append(
            {
                "label": label,
                "value": value,
                "code": code,
                "name": name,
                "metadata": entry.get("metadata")
                if isinstance(entry.get("metadata"), dict)
                else {},
            }
        )

    return ok(
        data={
            "items": items,
            "page": page,
            "pageSize": page_size,
            "total": total,
            "hasMore": offset + page_size < total,
        }
    )


REGISTRY: dict[str, Any] = {
    "query": _term_options_query,
}
