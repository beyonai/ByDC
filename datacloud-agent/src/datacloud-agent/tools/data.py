"""T_DATA_QUERY — natural-language data query (design §3.1).

Calls the external data-query microservice via HTTP.
Connection parameters come from ``DataServiceSettings`` (env vars
``DATACLOUD_DATA_SERVICE_*``).

Request example (from design)::

    POST /api/v1/query
    Headers:
        X-Tenant-Id: <tenant_id>
        X-User-Id:   <user_id>          ← injected at call time from TaskContext
        X-Session-Id:<session_id>       ← injected at call time from TaskContext
        X-System-Code: crm
        Authorization: Bearer <api_key>
    Body:
        {"question": "…", "view_id": "", "object_ids": []}
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def data_query(
    question: str,
    user_id: str,
    session_id: str,
    *,
    view_id: str = "",
    object_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Query the data service using a natural-language question.

    Args:
        question:   Natural-language data question (e.g. "超过一个月没有变更推进的商机").
        user_id:    Current user ID (forwarded as ``X-User-Id`` for auth & audit).
        session_id: Current session ID (forwarded as ``X-Session-Id``).
        view_id:    Optional view/scope filter.
        object_ids: Optional list of object IDs to scope the query.

    Returns:
        The raw JSON response body from the data service.
    """
    from datacloud_agent.config.env import DataServiceSettings  # noqa: PLC0415

    cfg = DataServiceSettings()
    url = cfg.base_url.rstrip("/") + cfg.query_path

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-User-Id": user_id,
        "X-Session-Id": session_id,
    }
    if cfg.tenant_id:
        headers["X-Tenant-Id"] = cfg.tenant_id
    if cfg.system_code:
        headers["X-System-Code"] = cfg.system_code
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "question": question,
        "view_id": view_id,
        "object_ids": object_ids or [],
    }

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
