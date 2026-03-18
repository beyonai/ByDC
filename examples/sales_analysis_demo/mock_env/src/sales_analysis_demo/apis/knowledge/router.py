"""知识构建结果通知接口。

提供两个端点：
  POST /knowledge/ingest/notify        — 接收知识构建完成后的回调通知
  GET  /knowledge/ingest/notify/latest — 读取最近一条通知（供测试断言）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/ingest", tags=["knowledge-notify"])

# 简单内存存储：只保留最新一条通知，生产环境应替换为持久化存储
_store: dict[str, Any] = {}


class IngestNotifyPayload(BaseModel):
    """知识构建回调 Payload（与 knowledge_build RunResult 字段对齐）。

    status 取值：
      precheck_failed — 预检未通过，未入库
      success         — 预检通过且入库成功
      import_failed   — 预检通过但入库失败（已回滚）
    """

    status: str
    folder_path: str | None = None
    precheck_errors: list[dict] = []
    stats: dict[str, Any] = {}
    error: str | None = None
    callback_notified: bool = False


@router.post("/notify", summary="接收知识构建回调通知")
async def receive_ingest_notify(payload: IngestNotifyPayload) -> dict:
    """接收知识构建完成（成功或失败）的回调通知，存入内存并返回确认。"""
    _store["latest"] = {
        "received_at": datetime.now(tz=timezone.utc).isoformat(),
        **payload.model_dump(),
    }
    logger.info(
        "knowledge ingest notify received: status=%s folder=%s",
        payload.status,
        payload.folder_path,
    )
    return {"ack": True, "status": payload.status}


@router.get("/notify/latest", summary="获取最新一条通知（供测试断言）")
def get_latest_notification() -> dict:
    """返回最近一次收到的知识构建通知，未收到时返回空对象。"""
    return _store.get("latest", {})


@router.delete("/notify/latest", summary="清除最新通知（供测试初始化）")
def clear_latest_notification() -> dict:
    """清除内存中保存的最新通知记录，用于测试前重置状态。"""
    _store.pop("latest", None)
    return {"cleared": True}
