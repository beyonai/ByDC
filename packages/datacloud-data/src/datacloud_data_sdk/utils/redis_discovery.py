"""Redis service-discovery configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class RedisDiscoveryConfig:
    """Redis configuration used by by-framework service discovery."""

    host: str
    port: int = 6379
    database: int = 0
    password: str | None = None
    username: str | None = None
    mode: Literal["standalone", "cluster"] = "standalone"
    cluster_nodes: tuple[tuple[str, int], ...] = ()


def load_redis_discovery_config() -> RedisDiscoveryConfig:
    """Load Redis discovery settings from standard runtime environment variables."""
    cluster_nodes = _parse_cluster_nodes(
        _env_first(
            "DATACLOUD_GATEWAY_REDIS_CLUSTER_HOST",
            "REDIS_CLUSTER_HOST",
        )
    )
    return RedisDiscoveryConfig(
        host=_env_first(
            "DATACLOUD_GATEWAY_REDIS_HOST",
            "REDIS_HOST",
        )
        or "localhost",
        port=_env_int_first(
            6379,
            "DATACLOUD_GATEWAY_REDIS_PORT",
            "REDIS_PORT",
        ),
        database=_env_int_first(
            0,
            "DATACLOUD_GATEWAY_REDIS_DB",
            "REDIS_DATABASE",
        ),
        password=_env_first(
            "DATACLOUD_GATEWAY_REDIS_PASSWORD",
            "REDIS_PASSWORD",
        )
        or None,
        username=_env_first(
            "DATACLOUD_GATEWAY_REDIS_USERNAME",
            "REDIS_USERNAME",
        )
        or None,
        mode="cluster" if cluster_nodes else "standalone",
        cluster_nodes=cluster_nodes,
    )


def init_redis_discovery(config: RedisDiscoveryConfig) -> Any:
    """Initialize by-framework Redis for service discovery."""

    from by_framework.common.config import RedisConfig
    from by_framework.common.redis_client import init_redis

    return init_redis(
        config=RedisConfig(
            host=config.host,
            port=config.port,
            db=config.database,
            password=config.password or "",
            username=config.username,
            mode=config.mode,
            cluster_nodes=list(config.cluster_nodes) or None,
        )
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


def _parse_cluster_nodes(value: str) -> tuple[tuple[str, int], ...]:
    nodes: list[tuple[str, int]] = []
    for raw_node in value.split(","):
        node = raw_node.strip()
        if not node:
            continue
        host, separator, port = node.rpartition(":")
        if not separator:
            host, port = node, "6379"
        nodes.append((host, int(port) if port else 6379))
    return tuple(nodes)
