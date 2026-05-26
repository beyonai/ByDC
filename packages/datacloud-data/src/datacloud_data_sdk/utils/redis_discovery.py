"""Redis service-discovery configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RedisDiscoveryConfig:
    """Redis configuration used by by-framework service discovery."""

    host: str
    port: int = 6379
    database: int = 0
    password: str | None = None
    username: str | None = None


def load_redis_discovery_config() -> RedisDiscoveryConfig:
    """Load Redis discovery settings from standard runtime environment variables."""
    return RedisDiscoveryConfig(
        host=_env_first("REDIS_HOST", "DATACLOUD_REDIS_HOST", "DATACLOUD_GATEWAY_REDIS_HOST")
        or "localhost",
        port=_env_int_first(
            6379,
            "REDIS_PORT",
            "DATACLOUD_REDIS_PORT",
            "DATACLOUD_GATEWAY_REDIS_PORT",
        ),
        database=_env_int_first(
            0,
            "REDIS_DATABASE",
            "DATACLOUD_REDIS_DATABASE",
            "DATACLOUD_GATEWAY_REDIS_DATABASE",
        ),
        password=_env_first(
            "REDIS_PASSWORD",
            "DATACLOUD_REDIS_PASSWORD",
            "DATACLOUD_GATEWAY_REDIS_PASSWORD",
        )
        or None,
        username=_env_first(
            "REDIS_USERNAME",
            "DATACLOUD_REDIS_USERNAME",
            "DATACLOUD_GATEWAY_REDIS_USERNAME",
        )
        or None,
    )


def _env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _env_int_first(default: int, *names: str) -> int:
    value = _env_first(*names)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
