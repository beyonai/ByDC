"""T_DATA_QUERY — natural-language data query tool.

Calls the external data-query microservice.
Connection params come from DataServiceSettings (env vars DATACLOUD_DATA_SERVICE_*).

user_id / session_id are optional audit headers forwarded to the service.
They default to env var DATACLOUD_DEFAULT_USER_ID / DATACLOUD_DEFAULT_SESSION_ID,
or "anonymous" / "default" if those are also unset.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def data_query(
    question: str,
    view_id: str = "",
    object_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Query business data using a natural-language question.

    Use this tool whenever the user asks about business data such as
    opportunities (商机), customers (客户), orders (订单), deals, or any CRM records.

    Args:
        question:   Natural-language question in Chinese or English.
                    E.g. "超过一个月没有变更推进的商机", "show all open deals".
        view_id:    Optional view/scope filter (leave empty if unsure).
        object_ids: Optional list of object IDs to narrow the query scope.

    Returns:
        The query result as a JSON object from the data service.
    """
    from datacloud_agent.config.env import DataServiceSettings  # noqa: PLC0415

    cfg = DataServiceSettings()
    url = cfg.base_url.rstrip("/") + cfg.query_path

    user_id = os.getenv("DATACLOUD_DEFAULT_USER_ID", "anonymous")
    session_id = os.getenv("DATACLOUD_DEFAULT_SESSION_ID", "default")

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

    payload: dict[str, Any] = {
        "question": question,
        "view_id": view_id,
        "object_ids": object_ids or [],
    }

    logger.info("[data_query] POST %s  question=%r  user=%s", url, question, user_id)

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()
        logger.info("[data_query] OK  status=%d", resp.status_code)
        return result
