"""个人 SQLite 动态表管理 — 通过服务发现调用 byclaw-sqlite HTTP API。

服务发现环境变量：
    REDIS_HOST / REDIS_PORT / REDIS_DATABASE / REDIS_PASSWORD / REDIS_USERNAME
        — 服务发现 Redis 连接参数（与运行环境共享）

SQLite 服务名规则：BYCLAW_EXE_{user_code}（如 BYCLAW_EXE_adminvip）
认证 token 从服务实例的 metadata.token 字段读取，无需额外环境变量。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, str] = {
    "STRING": "TEXT",
    "INTEGER": "INTEGER",
    "FLOAT": "REAL",
    "BOOLEAN": "INTEGER",
    "DATE": "TEXT",
}


# ── 服务发现 HTTP 调用 ─────────────────────────────────────────────────────────


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


def _execute_sql(sql: str, user_code: str) -> dict[str, Any]:
    """通过服务发现调用 byclaw-sqlite sqlExecute 接口。

    服务名规则：BYCLAW_EXE_{user_code}，每个用户对应独立的 SQLite 服务实例。
    认证 token 从服务实例 metadata.token 读取，通过 Authorization: Bearer {token} header 传递。
    """
    if not user_code:
        raise ValueError("user_code 不能为空，无法确定 SQLite 服务实例")

    service_name = f"BYCLAW_EXE_{user_code}"

    async def _call() -> dict[str, Any]:
        from by_framework.core.discovery import DiscoveryClient  # type: ignore[import-untyped]
        from by_framework.util.discovery_http_client import DiscoveryHttpClient  # type: ignore[import-untyped]
        from by_framework.util.http_client import RetryConfig  # type: ignore[import-untyped]

        _init_discovery_redis()
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            # 先 discover 拿到实例，从 metadata.token 取认证 token
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise RuntimeError(f"未找到 SQLite 服务实例: {service_name}")

            metadata = instance.metadata or {}
            token = metadata.get("token", "")

            async with DiscoveryHttpClient(discovery_client, retry_config=retry_config, health_threshold_ms=-1) as client:
                response = await client.post(
                    service_name,
                    "/plugins/byclaw-sqlite/sqlExecute",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    json={"sql": sql, "user_code": user_code},
                )
        finally:
            await discovery_client.close()

        body: dict[str, Any] = response.data if isinstance(response.data, dict) else {}
        if not body.get("ok"):
            err = body.get("error", {})
            raise RuntimeError(f"SQLite API error: {err.get('message', body)}")
        return body.get("data", {})

    return _run_async_in_thread(_call())


def _run_async_in_thread(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001
            error["exc"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


# ── 公开 API ──────────────────────────────────────────────────────────────────


def create_table(entity_code: str, fields: list[dict[str, Any]], user_code: str) -> None:
    """在个人 SQLite 中创建动态表（IF NOT EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
        fields: 字段列表，每项含 property_code 和 data_type。
        user_code: 操作用户编码，用于 SQLite key（BYCLAW_EXE_{user_code}）。
    """
    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for f in fields:
        col_name = f.get("property_code", "")
        if not col_name or col_name.lower() == "id":  # id 由系统自动生成，跳过
            continue
        sqlite_type = _TYPE_MAP.get(f.get("data_type", "STRING"), "TEXT")
        col_defs.append(f"{col_name} {sqlite_type}")

    ddl = f"CREATE TABLE IF NOT EXISTS {entity_code} ({', '.join(col_defs)})"
    logger.info("create_table: user=%s entity=%s", user_code, entity_code)
    _execute_sql(ddl, user_code)


def drop_table(entity_code: str, user_code: str = "") -> None:
    """删除个人 SQLite 中的动态表（IF EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
        user_code: 操作用户编码，默认从 USER_CODE 环境变量读取。
    """
    _user_code = user_code or os.environ.get("USER_CODE", "")
    ddl = f"DROP TABLE IF EXISTS {entity_code}"
    logger.info("drop_table: user=%s entity=%s", _user_code, entity_code)
    _execute_sql(ddl, _user_code)
