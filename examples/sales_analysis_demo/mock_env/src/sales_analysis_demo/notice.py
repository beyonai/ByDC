"""待办消息通知，与 todo.py _send_notice 行为一致."""

import asyncio
import logging
from http.cookies import SimpleCookie
from typing import Any

import httpx
import redis
from fastapi import Request

from sales_analysis_demo.config import settings

logger = logging.getLogger(__name__)


def _get_redis_client() -> redis.Redis:
    if settings.redis_url:
        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        decode_responses=True,
    )


def _resolve_user_real_id_sync(user_code: str | None) -> str | None:
    """同步：从 Redis 映射 user_code -> user_id."""
    if not user_code:
        return None
    try:
        client = _get_redis_client()
        real_id = client.get(f"SHARE_BFM_USER_CODE_{user_code}")
        return real_id or user_code
    except Exception as e:
        logger.warning("resolve_user_real_id failed: %s", e)
        return user_code


async def _resolve_user_real_id(user_code: str | None) -> str | None:
    """异步包装，避免阻塞."""
    return await asyncio.to_thread(_resolve_user_real_id_sync, user_code)


async def send_notice(notice_details: list[dict[str, Any]], request: Request | None) -> None:
    """调用外部通知接口，失败不阻断主流程."""
    if not settings.notice_url or not notice_details:
        return
    try:
        resolved = []
        for item in notice_details:
            new_item = dict(item)
            if "senderId" in new_item:
                new_item["senderId"] = await _resolve_user_real_id(
                    new_item.get("senderId")
                ) or new_item.get("senderId")
            if "targetId" in new_item:
                new_item["targetId"] = await _resolve_user_real_id(
                    new_item.get("targetId")
                ) or new_item.get("targetId")
            resolved.append(new_item)

        cookies = {}
        if request:
            if request.cookies:
                cookies = dict(request.cookies)
            elif request.headers.get("cookie"):
                c = SimpleCookie()
                c.load(request.headers.get("cookie", ""))
                for k, m in c.items():
                    cookies[k] = m.value

        async with httpx.AsyncClient() as client:
            await client.post(
                settings.notice_url,
                json={"noticeDetails": resolved},
                cookies=cookies,
                timeout=5,
            )
    except Exception as e:
        logger.warning("send_notice failed: %s", e)
