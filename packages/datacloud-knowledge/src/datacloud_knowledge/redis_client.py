"""Synchronous Redis client construction for DataCloud Knowledge."""

from __future__ import annotations

import os
from typing import Any


def _first_non_empty(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return default


def _cluster_nodes() -> list[tuple[str, int]]:
    value = _first_non_empty(
        "DATACLOUD_GATEWAY_REDIS_CLUSTER_HOST",
        "REDIS_CLUSTER_HOST",
    )
    nodes: list[tuple[str, int]] = []
    for raw_node in value.split(","):
        node = raw_node.strip()
        if not node:
            continue
        host, separator, port = node.rpartition(":")
        if not separator:
            host, port = node, "6379"
        nodes.append((host, int(port) if port else 6379))
    return nodes


def create_redis_client() -> Any:
    """Create a synchronous Redis client in standalone or cluster mode."""

    import redis
    from redis.cluster import ClusterNode, RedisCluster

    username = (
        _first_non_empty(
            "DATACLOUD_GATEWAY_REDIS_USERNAME",
            "REDIS_USERNAME",
        )
        or None
    )
    password = (
        _first_non_empty(
            "DATACLOUD_GATEWAY_REDIS_PASSWORD",
            "REDIS_PASSWORD",
        )
        or None
    )
    nodes = _cluster_nodes()
    if nodes:
        return RedisCluster(
            startup_nodes=[ClusterNode(host, port) for host, port in nodes],
            username=username,
            password=password,
            decode_responses=True,
        )
    return redis.Redis(
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
        username=username,
        password=password,
        decode_responses=True,
    )
