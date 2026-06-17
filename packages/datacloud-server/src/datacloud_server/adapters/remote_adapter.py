"""REMOTE 本体适配器 — 等价转发 HTTP POST 到外部本体服务。

规则:
    - HTTP method 转换: 内部 REST (GET/POST/PUT/DELETE) → 外部 POST
    - 参数注入: URL path 中的 sceneId/baseId 注入 POST body
    - 鉴权: authConfig 中的 Token 写入 HTTP Authorization header
    - 响应透传: 外部服务返回什么就透出什么，不做格式转换
    - 缓存: 元数据查询 TTL 5 分钟内存缓存（仅读操作）
"""
# ruff: noqa: ARG002, RUF002  # stub methods match Protocol; Chinese docstrings use full-width punctuation

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View

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

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
        """等价转发: GET → POST /OntologyEntityController/sceneDetails。

        Returns:
            外部服务返回的 objects 列表，透传不做格式转换。
        """
        cache_key = self._cache_key(base_id, scene_id, "objects")

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
        self, base_id: str, scene_id: str, object_code: str, action_code: str,
    ) -> dict | None:
        """REMOTE 暂不支持 get_action_detail，返回 None。"""
        return None

    # ── Scene: query ──────────────────────────────

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]:
        """REMOTE 暂不支持 query_scenes，返回空列表。"""
        return []

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """REMOTE 暂不支持 count_scenes。"""
        return 0

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict:
        """等价转发: POST /OntologyEntityController/sceneDetails。"""
        client = self._get_client()
        headers = self._build_auth_headers()
        body: dict[str, Any] = {"sceneId": scene_id}
        if view_code:
            body["viewCode"] = view_code
        if object_code:
            body["objectCode"] = object_code
        url = f"{self._source_url}/OntologyEntityController/sceneDetails"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result.get("data", {})

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict:
        """REMOTE 暂不支持 query_ontologies_by_scene。"""
        return {"data": [], "totalCount": 0}

    # ── 元数据: 写 ────────────────────────────────

    def create_object(self, base_id: str, scene_id: str, obj: ObjectType) -> ObjectType:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def update_object(self, base_id: str, scene_id: str, object_code: str, obj: ObjectType) -> ObjectType:
        """REMOTE 只读，禁止更新。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_view(self, base_id: str, scene_id: str, view: View) -> View:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def update_view(self, base_id: str, scene_id: str, view_code: str, view: View) -> View:
        """REMOTE 只读，禁止更新。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def update_relation(self, base_id: str, scene_id: str, rel_code: str, rel: Relation) -> Relation:
        """REMOTE 只读，禁止更新。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action: Action,
    ) -> Action:
        """REMOTE 只读，禁止创建。"""
        raise PermissionError("Remote ontology base is read-only")

    def update_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str, action: Action,
    ) -> Action:
        """REMOTE 只读，禁止更新。"""
        raise PermissionError("Remote ontology base is read-only")

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str,
    ) -> None:
        """REMOTE 只读，禁止删除。"""
        raise PermissionError("Remote ontology base is read-only")

    # ── 应用服务 ──────────────────────────────────

    def search_instances(
        self, base_id: str, *,
        object_code: str,
        select: list[str] | None = None,
        where: dict | None = None,
    ) -> dict:
        """等价转发: 不缓存，实时转发到 /InstanceController/search。"""
        client = self._get_client()
        headers = self._build_auth_headers()
        body: dict[str, Any] = {"objectCode": object_code}
        if select:
            body["select"] = select
        if where:
            body["where"] = where
        url = f"{self._source_url}/InstanceController/search"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def search_ontology(
        self, base_id: str, scene_id: str, *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        result_per_type: int = 5,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> dict:
        """等价转发: 不缓存，实时转发到 /search/ontology，注入 sceneId。"""
        client = self._get_client()
        headers = self._build_auth_headers()
        body: dict[str, Any] = {
            "keyword": keyword,
            "sceneId": scene_id,
            "queryType": query_type,
            "searchScope": search_scope,
            "resultPerType": result_per_type,
            "pageSize": page_size,
        }
        if object_code:
            body["objectCode"] = object_code
        if view_code:
            body["viewCode"] = view_code
        if property_code:
            body["propertyCode"] = property_code
        if page_token:
            body["pageToken"] = page_token
        url = f"{self._source_url}/search/ontology"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def search_ontology_batch(
        self, base_id: str, scene_id: str, *,
        keywords: list[str],
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        result_per_type: int = 5,
    ) -> list[dict]:
        """Batch search across multiple keywords via concurrent HTTP POST.

        Builds one request per keyword, posts concurrently with asyncio.gather,
        then tags each response's hits with ``_keyword_index`` (int).
        """
        valid_keywords = [k for k in keywords if k]
        if not valid_keywords:
            return []

        url = f"{self._source_url}/search/ontology"
        headers = self._build_auth_headers()

        return asyncio.run(
            self._search_ontology_batch_async(
                url, headers, valid_keywords,
                scene_id=scene_id,
                search_scope=search_scope,
                result_per_type=result_per_type,
                object_code=object_code,
                view_code=view_code,
            )
        )

    async def _search_ontology_batch_async(
        self,
        url: str,
        headers: dict[str, str],
        keywords: list[str],
        *,
        scene_id: str,
        search_scope: str,
        result_per_type: int,
        object_code: list[str] | None,
        view_code: list[str] | None,
    ) -> list[dict]:
        """Internal async implementation: concurrent POSTs via httpx.AsyncClient."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            tasks = [
                client.post(
                    url,
                    json={
                        "keyword": kw,
                        "sceneId": scene_id,
                        "queryType": "vector",
                        "searchScope": search_scope,
                        "resultPerType": result_per_type,
                        "pageSize": 20,
                        **({"objectCode": object_code} if object_code else {}),
                        **({"viewCode": view_code} if view_code else {}),
                    },
                    headers=headers,
                )
                for kw in keywords
            ]
            responses = await asyncio.gather(*tasks)

        hits: list[dict] = []
        for i, resp in enumerate(responses):
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            for hit in data.get("metadata", []):
                hit["_keyword_index"] = i
                hits.append(hit)
            for hit in data.get("instances", []):
                hit["_keyword_index"] = i
                hits.append(hit)
        return hits

    def graph_query(
        self, base_id: str, scene_id: str, *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict:
        """REMOTE 暂不支持 graph_query，返回空结果。"""
        return {"nodes": [], "edges": []}

    def graph_path(
        self, base_id: str, scene_id: str, *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict:
        """REMOTE 暂不支持 graph_path，返回空结果。"""
        return {"path": [], "edges": [], "hops": -1}

    # ── OWL Import ──

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        """REMOTE 只读，禁止导入。"""
        raise PermissionError("Remote ontology base is read-only")

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
