"""Redis service-discovery configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RedisDiscoveryConfig:
    """Redis configuration used by by-framework service discovery."""

    host: str
    port: int = 6379
    database: int = 0
    password: str | None = None
    username: str | None = None
    # 集群模式：非空时忽略 host/port，走 RedisCluster
    cluster_nodes: list[tuple[str, int]] = field(default_factory=list)

    @property
    def is_cluster(self) -> bool:
        return bool(self.cluster_nodes)


def load_redis_discovery_config() -> RedisDiscoveryConfig:
    """Load Redis discovery settings from standard runtime environment variables.

    集群判定：优先读 DATACLOUD_GATEWAY_REDIS_CLUSTER_HOST，再 fallback REDIS_CLUSTER_HOST。
    格式：逗号分隔的 host:port 列表，如 10.0.0.1:6371,10.0.0.2:6372。
    集群模式下 host/port/database 字段仍会被填充（供调用方日志使用），但实际连接走 cluster_nodes。
    """
    cluster_hosts = (
        _env_first("DATACLOUD_GATEWAY_REDIS_CLUSTER_HOST", "REDIS_CLUSTER_HOST") or ""
    ).strip()

    nodes: list[tuple[str, int]] = []
    if cluster_hosts:
        for node in cluster_hosts.split(","):
            node = node.strip()
            if not node:
                continue
            host, _, port_str = node.rpartition(":")
            nodes.append((host, int(port_str) if port_str else 6379))

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
        cluster_nodes=nodes,
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
