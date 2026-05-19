"""Skill 公共库：服务发现、认证、HTTP 请求封装。

服务发现使用 by_framework，Redis 连接参数复用运行环境的 REDIS_* 变量。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)


def _init_discovery_redis() -> None:
    """全局初始化服务发现 Redis（幂等）。"""
    from by_framework.common.redis_client import init_redis  # type: ignore[import-untyped]

    init_redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DATABASE", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        username=os.getenv("REDIS_USERNAME") or None,
    )


def post_json(path: str, payload: dict[str, Any], service_env: str = "BE_DOMAINNAME") -> Any:
    """通过服务发现调用指定服务的 POST 接口。

    Args:
        path: 接口路径，如 "/auth/privilegeGrant/listResourceUseAuth"
        payload: 请求体
        service_env: 服务名称的环境变量名，默认 BE_DOMAINNAME
    """
    service_name = os.environ.get(service_env, "").strip()
    if not service_name:
        raise ValueError(f"{service_env} 环境变量未配置")

    token = os.environ.get("BEYOND_TOKEN", "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Beyond-Token"] = token

    return _run_async_in_thread(_post_via_discovery(service_name, path, payload, headers))


async def _post_via_discovery(
    service_name: str,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> Any:
    from by_framework.core.discovery import DiscoveryClient  # type: ignore[import-untyped]
    from by_framework.util.discovery_http_client import DiscoveryHttpClient  # type: ignore[import-untyped]
    from by_framework.util.http_client import RetryConfig  # type: ignore[import-untyped]

    _init_discovery_redis()
    discovery_client = DiscoveryClient(cache_interval=5)
    retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
    try:
        async with DiscoveryHttpClient(discovery_client, retry_config=retry_config, health_threshold_ms=-1) as client:
            response = await client.post(service_name, path, headers=headers, json=payload)
    finally:
        await discovery_client.close()

    body: dict[str, Any] = response.data if isinstance(response.data, dict) else {}
    if not response.is_success or body.get("code", 0) != 0:
        raise ValueError(f"HTTP {response.status_code} {service_name}{path}: {body.get('msg', body)}")
    return body.get("data")


def _run_async_in_thread(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            error["exc"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def delete_resource_by_code(resource_code: str) -> None:
    """通过 resourceCode 直接下架个人本体。"""
    data = post_json(
        path="/byaiService/tool/deleteResourceByCodeAndOwnerType",
        payload={"resourceCode": resource_code, "ownerType": "personal"},
    )
    if not data or data.get("code") != 0:
        raise RuntimeError(f"下架本体失败: {data}")
