"""进程级 OWL Script 跨调用缓存。

OWL Script 在执行时无法直接访问 AgentState，也无法通过函数参数传递大体积数据。
本模块提供一个进程级全局字典，供 OWL Script 之间共享数据，典型用途：

  - 某个 Script（如 get_spans）从外部 API 拉取大体积原始数据写入缓存
  - 后续 Script（如 get_early_span / get_llm_metrics 等）按 key 读取，
    避免重复调用 API，同时保证大体积 JSON 永远不直接传给 LLM

Key design：
  - 进程级全局 dict，不写硬盘，不进 LangGraph checkpoint
  - key 由调用方自定义（通常是请求级唯一标识，如 trace_id）
  - 不同请求之间通过 key 隔离，互不干扰
  - 带 TTL 自动过期（默认 300 秒），防止内存无限增长
  - OWL Script 通过以下方式访问，不依赖 context 对象：
      from datacloud_analysis.tools.owl_script_cache import get_cache, set_cache
"""

from __future__ import annotations

import time
from typing import Any

# 默认 TTL：300 秒（一次诊断对话通常在 5 分钟内完成）
_DEFAULT_TTL: int = 300

# 进程级缓存：key → (value, expire_at)
_CACHE: dict[str, tuple[Any, float]] = {}


def set_cache(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """写入缓存。

    Args:
        key:   全局唯一标识，由调用方定义（如 trace_id、agent_id 等）。
        value: 任意对象。
        ttl:   过期秒数，默认 300 秒。
    """
    _CACHE[key] = (value, time.monotonic() + ttl)


def get_cache(key: str, default: Any = None) -> Any:
    """读取缓存。过期的条目视为未命中并自动清除。

    Args:
        key:     写入时使用的 key。
        default: 缓存未命中或已过期时的默认值，默认为 None。

    Returns:
        缓存值；未命中或已过期返回 default。
    """
    entry = _CACHE.get(key)
    if entry is None:
        return default
    value, expire_at = entry
    if time.monotonic() > expire_at:
        del _CACHE[key]
        return default
    return value


def clear_cache(key: str | None = None) -> None:
    """清除缓存。

    Args:
        key: 指定时只清除该 key；为 None 时清除全部（含未过期条目）。
    """
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


# ── 兼容旧接口（保留至所有 OWL Script 完成迁移后删除）──────────────────────
def cache_observations(trace_id: str, observations: list[dict[str, Any]]) -> None:
    """已废弃，请改用 set_cache(trace_id, observations)。"""
    set_cache(trace_id, observations)


def get_cached_observations(trace_id: str) -> list[dict[str, Any]]:
    """已废弃，请改用 get_cache(trace_id, [])。"""
    return get_cache(trace_id, [])
