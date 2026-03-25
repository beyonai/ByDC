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
    from datacloud_analysis.config.env import DataServiceSettings  # noqa: PLC0415

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

    logger.info("[data_query] POST %s  question=%r  user=%s  timeout=%ds", url, question, user_id, cfg.timeout)

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            
            if result.get("code") == 0:
                data = result.get("data", {})
                if data.get("resultType") == "normal" and "records" in data:
                    records = data["records"]
                    meta = data.get("meta", {})
                    total = data.get("total", len(records))
                    
                    try:
                        from gateway_sdk.worker.sandbox.hook_sandbox import active_workspace
                        workspace_dir = active_workspace.get()
                    except ImportError:
                        workspace_dir = None
                        
                    if not workspace_dir:
                        workspace_dir = os.path.join(os.getenv("DATACLOUD_GATEWAY_WORKSPACE_DIR", "/tmp/datacloud"), session_id)
                        
                    import uuid
                    import json
                    
                    file_name = f"data_query_{uuid.uuid4().hex[:8]}.jsonl"
                    file_path = os.path.join(workspace_dir, file_name)
                    os.makedirs(workspace_dir, exist_ok=True)
                    
                    with open(file_path, "w", encoding="utf-8") as f:
                        meta_row = {
                            "_type": "meta", 
                            "columns": meta.get("columns", []), 
                            "total": total, 
                            "download_url": meta.get("download_url")
                        }
                        f.write(json.dumps(meta_row, ensure_ascii=False) + "\n")
                        for row in records:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    
                    return {
                        "status": "success",
                        "file_path": file_path,
                        "total": total,
                        "columns": meta.get("columns", []),
                        "preview": records[:5],
                        "original_download_url": meta.get("download_url"),
                        "overflow_notice": data.get("overflow_notice", "")
                    }
                    
            logger.info("[data_query] OK  status=%d", resp.status_code)
            return result
    except httpx.ReadTimeout:
        logger.error("[data_query] ReadTimeout after %ds — data service may be slow or overloaded", cfg.timeout)
        return {"error": "data_query_timeout", "message": f"数据服务响应超时（{cfg.timeout}s），请稍后重试或增大 DATACLOUD_DATA_SERVICE_TIMEOUT"}
