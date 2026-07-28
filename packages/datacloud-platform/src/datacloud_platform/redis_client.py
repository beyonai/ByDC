"""Redis configuration shared by DataCloud Platform integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RedisSettings:
    """Resolved standalone or cluster Redis settings."""

    cluster_nodes: tuple[tuple[str, int], ...]
    host: str
    port: int
    db: int
    username: str | None
    password: str | None


def _first_non_empty(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
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


def get_redis_settings() -> RedisSettings:
    """Load DataCloud-prefixed settings with generic Redis fallbacks."""

    return RedisSettings(
        cluster_nodes=_parse_cluster_nodes(
            _first_non_empty(
                "DATACLOUD_GATEWAY_REDIS_CLUSTER_HOST",
                "REDIS_CLUSTER_HOST",
            )
        ),
        host=_first_non_empty(
            "DATACLOUD_GATEWAY_REDIS_HOST",
            "REDIS_HOST",
            default="localhost",
        ),
        port=int(
            _first_non_empty(
                "DATACLOUD_GATEWAY_REDIS_PORT",
                "REDIS_PORT",
                default="6379",
            )
        ),
        db=int(
            _first_non_empty(
                "DATACLOUD_GATEWAY_REDIS_DB",
                "REDIS_DATABASE",
                default="0",
            )
        ),
        username=_first_non_empty(
            "DATACLOUD_GATEWAY_REDIS_USERNAME",
            "REDIS_USERNAME",
        )
        or None,
        password=_first_non_empty(
            "DATACLOUD_GATEWAY_REDIS_PASSWORD",
            "REDIS_PASSWORD",
        )
        or None,
    )


def create_async_redis_client(settings: RedisSettings | None = None) -> Any:
    """Create an async Redis client for standalone or cluster mode."""

    from redis.asyncio import Redis
    from redis.asyncio.cluster import ClusterNode, RedisCluster

    resolved = settings or get_redis_settings()
    if resolved.cluster_nodes:
        return RedisCluster(
            startup_nodes=[
                ClusterNode(host, port) for host, port in resolved.cluster_nodes
            ],
            username=resolved.username,
            password=resolved.password,
            decode_responses=True,
        )
    return Redis(
        host=resolved.host,
        port=resolved.port,
        db=resolved.db,
        username=resolved.username,
        password=resolved.password,
        decode_responses=True,
    )


def init_framework_redis(settings: RedisSettings | None = None) -> Any:
    """Initialize by-framework's shared Redis client in either mode."""

    from by_framework.common.config import RedisConfig
    from by_framework.common.redis_client import init_redis

    resolved = settings or get_redis_settings()
    config = RedisConfig(
        host=resolved.host,
        port=resolved.port,
        db=resolved.db,
        username=resolved.username,
        password=resolved.password or "",
        mode="cluster" if resolved.cluster_nodes else "standalone",
        cluster_nodes=list(resolved.cluster_nodes) or None,
    )
    return init_redis(config=config)
