"""RPC handlers for knowledge-base action execution.

Methods:
  - invokeAction: Execute a KB action (write_*, search_*, search_by_file_name_*,
    merge_write_*, delete_kb_*) via the ontology loader + execution backend pipeline.

This is the same path that OntologyLoader.invoke_action() uses internally:
  load_ontology → inject_virtual_actions → execute_action(loader, object_code, action_code, args)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok
from datacloud_data_sdk.ontology.loader import OntologyLoader

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


def _unwrap_mcp_result(mcp: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the MCP envelope returned by ActionExecutor.execute().

    ActionExecutor wraps its result as:
      {"content": [{"type": "text", "text": "<json>"}], "isError": false}

    The inner JSON has shape:
      {"code": 0, "message": "success", "data": {"result_type": ..., "records": [...], ...}}

    Returns the inner ``data`` dict, or re-raises if the inner code signals failure.
    """
    content = mcp.get("content") or []
    if not content:
        return mcp

    text = content[0].get("text", "") if isinstance(content[0], dict) else ""
    if not text:
        return mcp

    try:
        inner = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return mcp

    inner_data: dict[str, Any] = inner.get("data") or {}
    inner_code: int = int(inner.get("code") or 0)

    if inner_code not in (0, 200):
        raise RuntimeError(
            inner.get("message") or f"KB action failed (code={inner_code})"
        )

    return {
        "records": inner_data.get("records") or [],
        "total": inner_data.get("total")
        or inner_data.get("meta", {}).get("total")
        or 0,
        "meta": inner_data.get("meta") or {},
    }


# ── invokeAction ──────────────────────────────────────────────────────────────


async def _invoke_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Execute a KB action via ontology loader + execution backend.

    Mirrors the SDK call:
      loader.get_object(object_code).invoke_action(action_code, arguments)

    Params:
      - objectCode / object_code (str, required): Ontology object code.
      - actionCode / action_code (str, required): Action code to invoke,
          e.g. write_Ability, search_Ability, merge_write_Ability, delete_kb_Ability.
      - arguments (dict, optional): Action arguments forwarded verbatim
          to the execution backend. Common fields:
            - source_path (str): Document path, must start with /.
            - content (str): Markdown document body.
            - labels (dict): Metadata labels.
            - file_description (str): Human-readable file description.
            - query (str): Search query text (for search_* actions).
            - select (list[str]): Field list (for search_* actions).
            - filters (list): Filter conditions (for search_* actions).
            - limit (int): Max records (default depends on action).
    """
    object_code = str(params.get("object_code") or params.get("objectCode") or "")
    if not object_code:
        raise ValueError("object_code / objectCode is required")

    action_code = str(params.get("action_code") or params.get("actionCode") or "")
    if not action_code:
        raise ValueError("action_code / actionCode is required")

    arguments: dict[str, Any] = params.get("arguments") or {}
    base_id: str = str(params.get("base_id") or DEFAULT_BASE_ID)

    loader = platform._load_ontology_cached(base_id)  # noqa: SLF001
    if isinstance(loader, OntologyLoader):
        loader.configure(platform=platform)
    platform.inject_virtual_actions(base_id, loader)

    mcp_result = await platform.execute_action(
        base_id, loader, object_code, action_code, arguments
    )
    data = _unwrap_mcp_result(mcp_result)
    return ok(data=data)


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, Any] = {
    "invokeAction": _invoke_action,
}
