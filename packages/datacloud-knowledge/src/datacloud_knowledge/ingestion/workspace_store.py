"""暂存工作区状态的抽象接口及实现。

支持两种后端：
- RedisWorkspaceStore：生产环境，通过 ONTOLOGY_REDIS_* 环境变量配置。
- LocalFileWorkspaceStore：本地开发/测试，通过 ONTOLOGY_WORKSPACE_DIR 配置。

工厂函数 get_workspace_store() 通过 ONTOLOGY_STORE 环境变量（redis/local）选择后端。
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceStore(ABC):
    """暂存工作区状态的抽象接口。"""

    @abstractmethod
    def load(self, key: str) -> dict[str, Any]:
        """读取暂存状态，key 不存在时返回空 dict。"""

    @abstractmethod
    def save(self, key: str, state: dict[str, Any], ttl: int = 3600) -> None:
        """写入暂存状态，ttl 单位秒（文件后端忽略 ttl）。"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除暂存状态（提交成功后清理）。"""


class RedisWorkspaceStore(WorkspaceStore):
    """生产环境：使用 Redis 存储。

    环境变量：
        ONTOLOGY_REDIS_HOST      默认 localhost
        ONTOLOGY_REDIS_PORT      默认 6379
        ONTOLOGY_REDIS_DB        默认 0
        ONTOLOGY_REDIS_PASSWORD  默认空
        ONTOLOGY_REDIS_USERNAME  默认空
    """

    _KEY_PREFIX = "ontology_workspace:"

    def __init__(self) -> None:
        import redis  # type: ignore[import-untyped]

        self._client: redis.Redis[str] = redis.Redis(
            host=os.getenv("ONTOLOGY_REDIS_HOST", "localhost"),
            port=int(os.getenv("ONTOLOGY_REDIS_PORT", "6379")),
            db=int(os.getenv("ONTOLOGY_REDIS_DB", "0")),
            password=os.getenv("ONTOLOGY_REDIS_PASSWORD") or None,
            username=os.getenv("ONTOLOGY_REDIS_USERNAME") or None,
            decode_responses=True,
        )

    def _full_key(self, key: str) -> str:
        return f"{self._KEY_PREFIX}{key}"

    def load(self, key: str) -> dict[str, Any]:
        raw = self._client.get(self._full_key(key))
        if not raw:
            return {}
        result: dict[str, Any] = json.loads(raw)
        return result

    def save(self, key: str, state: dict[str, Any], ttl: int = 3600) -> None:
        self._client.setex(self._full_key(key), ttl, json.dumps(state, ensure_ascii=False))

    def delete(self, key: str) -> None:
        self._client.delete(self._full_key(key))


class LocalFileWorkspaceStore(WorkspaceStore):
    """本地开发/测试：使用文件存储。

    环境变量：
        ONTOLOGY_WORKSPACE_DIR   默认 ~/.ontology_workspace
    """

    def __init__(self) -> None:
        base = os.getenv("ONTOLOGY_WORKSPACE_DIR", str(Path.home() / ".ontology_workspace"))
        self._base = Path(base)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self._base / f"{safe}.json"

    def load(self, key: str) -> dict[str, Any]:
        p = self._path(key)
        if not p.exists():
            return {}
        result: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        return result

    def save(self, key: str, state: dict[str, Any], ttl: int = 3600) -> None:
        self._path(key).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


def get_workspace_store() -> WorkspaceStore:
    """工厂函数：ONTOLOGY_STORE=redis（默认）或 local。"""
    store_type = os.getenv("ONTOLOGY_STORE", "redis").lower().strip()
    if store_type == "local":
        return LocalFileWorkspaceStore()
    return RedisWorkspaceStore()
