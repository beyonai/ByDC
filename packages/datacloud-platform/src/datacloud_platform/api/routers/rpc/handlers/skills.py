"""RPC handler for 'skills' service.

Replicates the logic of GET /api/v1/skills/package (skills_routes.py).
Uses get_request_loader_snapshot(request) to access the loader runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.loader_runtime import get_request_loader_snapshot

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


async def _skills_get_package(
    platform: DatacloudPlatform, params: dict[str, Any], request: Request
) -> Any:
    tenant_id = request.headers.get("X-Tenant-Id", "")
    if not tenant_id:
        raise ValueError("X-Tenant-Id required")

    view_id = params.get("view_id")
    object_ids_str = params.get("object_ids")
    object_ids_list: list[str] = []
    if object_ids_str:
        object_ids_list = [
            s.strip() for s in str(object_ids_str).split(",") if s.strip()
        ]

    has_view_id = view_id is not None and str(view_id).strip() != ""
    has_object_ids = len(object_ids_list) > 0

    if not has_view_id and not has_object_ids:
        raise ValueError("view_id or object_ids required (at least one)")

    snapshot = await get_request_loader_snapshot(request, reason="skills_package")
    if snapshot is None:
        raise ValueError("OntologyLoader not initialized")
    loader = snapshot.loader

    tool_list_mode = request.headers.get("X-Tool-List-Mode", "unified")
    if tool_list_mode not in ("unified", "per_object"):
        tool_list_mode = "unified"

    from datacloud_platform.execution.skill_package_generator import (
        SkillPackageGenerator,
    )

    safe_view_id = str(view_id).strip() if view_id is not None else None
    generator = SkillPackageGenerator(loader)
    result = generator.generate(
        view_id=safe_view_id,
        object_ids=object_ids_list if has_object_ids else None,
        tool_list_mode=tool_list_mode,
    )
    return result


REGISTRY: dict[str, Any] = {
    "getPackage": _skills_get_package,
}
