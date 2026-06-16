"""REMOTE 本体适配器 — 等价转发 HTTP POST 到外部本体服务。

规则:
    - HTTP method 转换: 内部 REST (GET/POST/PUT/DELETE) → 外部 POST
    - 参数注入: URL path 中的 sceneId/baseId 注入 POST body
    - 鉴权: authConfig 中的 Token 写入 HTTP Authorization header
    - 响应透传: 外部服务返回什么就透出什么，不做格式转换
    - 缓存: 元数据查询 TTL 5 分钟内存缓存（仅读操作）
"""

# ruff: noqa: RUF002, ARG002

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class _CacheEntry:
    """TTL 缓存条目。"""

    __slots__ = ("data", "expires_at")

    def __init__(self, data: object, ttl: int = 300) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl

    @property
    def is_expired(self) -> bool:
        """是否已过期。"""
        return time.monotonic() > self.expires_at


class RemoteOntologyAdapter:
    """REMOTE 本体适配器 — 等价转发 HTTP POST。

    读操作通过 POST 转发到外部本体服务，5 分钟 TTL 缓存。
    写操作统一返回 PermissionError("Remote ontology base is read-only")。
    """

    def __init__(
        self,
        source_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url.rstrip("/")
        self._auth_config = auth_config
        self._client: httpx.Client | None = None
        self._cache: dict[tuple[str, str, str], _CacheEntry] = {}

    def _get_client(self) -> httpx.Client:
        """惰性创建 httpx 客户端。"""
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def _cache_key(self, base_id: str, scene_id: str, resource: str) -> tuple[str, str, str]:
        """生成缓存键。"""
        return (base_id, scene_id, resource)

    # ── 元数据: 读 ────────────────────────────────

    def list_scenes(self, base_id: str) -> list[dict]:
        """REMOTE 暂不支持 list_scenes，返回空列表。"""
        return []

    def get_scene(self, base_id: str, scene_id: str) -> dict | None:
        """REMOTE 暂不支持 get_scene，返回 None。"""
        return None

    def get_objects(
        self,
        base_id: str,
        scene_id: str,
        *,
        use_cache: bool = True,
    ) -> list[dict]:
        """等价转发: GET → POST /OntologyEntityController/sceneDetails。

        Args:
            base_id: 本体库 ID
            scene_id: 场景 ID
            use_cache: 是否使用 TTL 缓存，默认 True

        Returns:
            外部服务返回的 objects 列表，透传不做格式转换。
        """
        cache_key = self._cache_key(base_id, scene_id, "objects")

        if use_cache:
            entry = self._cache.get(cache_key)
            if entry is not None and not entry.is_expired:
                return entry.data  # type: ignore[no-any-return]

        client = self._get_client()
        headers = self._build_auth_headers()
        body = {"sceneId": scene_id}

        url = f"{self._source_url}/OntologyEntityController/sceneDetails"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()

        data = result.get("data", {}).get("objects", [])
        if use_cache:
            self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        """REMOTE 暂不支持 get_object_detail，返回 None。"""
        return None

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        """REMOTE 暂不支持 get_views，返回空列表。"""
        return []

    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None:
        """REMOTE 暂不支持 get_view_detail，返回 None。"""
        return None

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        """REMOTE 暂不支持 get_relations，返回空列表。"""
        return []

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        """REMOTE 暂不支持 get_relation_detail，返回 None。"""
        return None

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]:
        """REMOTE 暂不支持 get_datasources，返回空列表。"""
        return []

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        """REMOTE 暂不支持 get_datasource_detail，返回 None。"""
        return None

    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]:
        """REMOTE 暂不支持 get_actions，返回空列表。"""
        return []

    def get_action_detail(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict | None:
        """REMOTE 暂不支持 get_action_detail，返回 None。"""
        return None

    # ── 元数据: 写 ────────────────────────────────

    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def update_object(self, base_id: str, scene_id: str, object_code: str, obj_data: dict) -> dict:
        """REMOTE 只读，禁止更新。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_view(self, base_id: str, scene_id: str, view_data: dict) -> dict:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_relation(self, base_id: str, scene_id: str, rel_data: dict) -> dict:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_datasource(self, base_id: str, scene_id: str, ds_data: dict) -> dict:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action_data: dict
    ) -> dict:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    # ── 应用服务 ──────────────────────────────────

    def search_instances(self, base_id: str, query: dict) -> dict:
        """等价转发: 不缓存，实时转发到 /InstanceController/search。"""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/InstanceController/search"
        response = client.post(url, json=query, headers=headers)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def search_ontology(self, base_id: str, scene_id: str, request: dict) -> dict:
        """等价转发: 不缓存，实时转发到 /search/ontology，注入 sceneId。"""
        client = self._get_client()
        headers = self._build_auth_headers()
        body = {**request, "sceneId": scene_id}
        url = f"{self._source_url}/search/ontology"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def graph_query(self, base_id: str, scene_id: str, query: dict) -> dict:
        """REMOTE 暂不支持 graph_query，返回空结果。"""
        return {"nodes": [], "edges": []}

    # ── 辅助方法 ──────────────────────────────────

    def _build_auth_headers(self) -> dict[str, str]:
        """根据 auth_config 构建认证头。"""
        if not self._auth_config:
            return {}
        auth_type = self._auth_config.get("type", "").lower()
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {self._auth_config.get('token', '')}"}
        if auth_type == "api_key":
            header_name = self._auth_config.get("headerName", "X-API-Key")
            return {header_name: self._auth_config.get("apiKey", "")}
        return {}

    def close(self) -> None:
        """关闭 httpx 客户端，释放连接资源。"""
        if self._client is not None:
            self._client.close()
            self._client = None
