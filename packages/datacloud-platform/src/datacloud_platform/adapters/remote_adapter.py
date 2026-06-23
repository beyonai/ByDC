"""Remote adapter — HTTP-forwarding backends for remote ontology & knowledge services.

Refactored from datacloud_server/adapters/remote_adapter.py into two separate
Platform Backend classes: RemoteOntologyBackend (OntologyBackend Protocol) and
RemoteKnowledgeBackend (KnowledgeBackend Protocol).
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any, cast

logger = logging.getLogger(__name__)


class _CacheEntry:
    """TTL cache entry for read operations."""

    __slots__ = ("data", "expires_at")

    def __init__(self, data: Any, ttl: int = 300) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl

    @property
    def is_expired(self) -> bool:
        """Whether this cache entry has expired."""
        return time.monotonic() > self.expires_at


class RemoteOntologyBackend:
    """OntologyBackend that forwards read operations to a remote HTTP service.

    Write operations always raise ``PermissionError``.
    """

    def __init__(
        self,
        source_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url.rstrip("/")
        self._auth_config = auth_config
        self._client: Any = None
        self._cache: dict[str, _CacheEntry] = {}

    def _get_client(self) -> Any:
        """Lazy httpx client creation."""
        if self._client is None:
            import httpx  # noqa: PLC0415

            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers from auth_config."""
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
        """Close the underlying HTTP client."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None

    # ── OntologyBackend Protocol ────────────────────────────────────────

    def parse_owl(self, directory: Any) -> Any:
        """Remote ontology is read-only — OWL parsing is not supported."""
        from datacloud_platform.models.shared import ParsedOwlContent

        return ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Any) -> Any:
        """Remote ontology is read-only — loading is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def load_terms(self, loader: Any, *, library_id: str = "PERSONAL_LIB") -> Any:
        """Remote ontology is read-only — term loading is not supported."""
        return None

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def drop_table(self, object_code: str) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def get_objects(self, loader: Any, base_id: str) -> list[Any]:
        """Fetch objects from remote scene details endpoint.

        5-minute TTL cache on the response.
        """
        cache_key = f"objects:{base_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)

        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listObjects"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = cast("list[Any]", result.get("data", {}).get("objects", []))
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_object_detail(self, loader: Any, object_code: str) -> Any | None:
        """Remote ontology does not support per-object detail."""
        return None

    # -- View CRUD (remote, read-only) --

    def get_views(self, base_id: str) -> list[Any]:
        """Fetch views from remote endpoint."""
        cache_key = f"views:{base_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listViews"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = cast("list[Any]", result.get("data", {}).get("views", []))
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_view_detail(self, base_id: str, view_code: str) -> Any | None:
        """Look up view detail from cached views."""
        for v in self.get_views(base_id):
            if v.get("viewCode") == view_code:
                return v
        return None

    def create_view(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_view(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_view(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Relation CRUD (remote, read-only) --

    def get_relations(self, base_id: str) -> list[Any]:
        """Fetch relations from remote endpoint."""
        cache_key = f"relations:{base_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listRelations"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = cast("list[Any]", result.get("data", {}).get("relations", []))
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_relation_detail(self, base_id: str, rel_code: str) -> Any | None:
        """Look up relation detail from cached relations."""
        for r in self.get_relations(base_id):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_relation(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_relation(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Datasource CRUD (remote, read-only) --

    def get_datasources(self, base_id: str) -> list[Any]:
        """Fetch datasources from remote endpoint."""
        cache_key = f"datasources:{base_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listDatasources"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = cast("list[Any]", result.get("data", {}).get("dbsources", []))
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_datasource_detail(self, base_id: str, db_id: str) -> Any | None:
        """Look up datasource from cached datasources."""
        for ds in self.get_datasources(base_id):
            db_list = ds.get("db", [])
            if db_list and isinstance(db_list, list) and db_list:
                if str(db_list[0].get("dbId", "")) == db_id:
                    return ds
            elif str(ds.get("dbId", ds.get("db_id", ""))) == db_id:
                return ds
        return None

    def create_datasource(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Action CRUD (remote, read-only) --

    def get_actions(self, base_id: str, object_code: str) -> list[Any]:
        """Fetch actions from remote endpoint."""
        cache_key = f"actions:{base_id}:{object_code}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listActions"
        response = client.post(
            url,
            json={"baseId": base_id, "objectCode": object_code},
            headers=headers,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = cast("list[Any]", result.get("data", {}).get("actions", []))
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def get_action_detail(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> Any | None:
        """Look up action from cached actions."""
        for a in self.get_actions(base_id, object_code):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        obj: Any,
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Scene management (remote, read-only) --

    def list_scenes(self, base_id: str) -> list[Any]:
        """Fetch scenes from remote endpoint."""
        cache_key = f"scenes:{base_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("list[Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listScenes"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        data: list[Any] = response.json()
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def query_scenes(self, base_id: str, keyword: str | None) -> list[Any]:
        """Query scenes with keyword filter (client-side filter on cached)."""
        scenes = self.list_scenes(base_id)
        if not keyword:
            return scenes
        kw = keyword.strip().lower()
        return [
            s
            for s in scenes
            if kw in str(s.get("sceneName", "")).lower()
            or kw in str(s.get("sceneCode", "")).lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching keyword."""
        return len(self.query_scenes(base_id, keyword))

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch scene details from remote endpoint."""
        cache_key = f"scene_details:{base_id}:{scene_id}:{view_code}:{object_code}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return cast("dict[str, Any]", entry.data)
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/sceneDetails"
        body: dict[str, Any] = {"sceneId": scene_id}
        if view_code:
            body["viewCode"] = ",".join(view_code)
        if object_code:
            body["objectCode"] = ",".join(object_code)
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Remote ontology is read-only — pagination not supported."""
        _ = base_id, scene_id, page, page_size, keyword
        logger.debug("Remote ontology: query_ontologies_by_scene not supported")
        return {"data": [], "totalCount": 0}

    # -- Scene CRUD (remote, read-only) --

    def create_scene(self, base_id: str, scene: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Object CRUD (remote, read-only) --

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")


class RemoteKnowledgeBackend:
    """KnowledgeBackend that forwards search operations to a remote HTTP service.

    Graph query is not supported — always returns empty.
    """

    def __init__(
        self,
        source_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url.rstrip("/")
        self._auth_config = auth_config
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy httpx client creation."""
        if self._client is None:
            import httpx  # noqa: PLC0415

            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers from auth_config."""
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
        """Close the underlying HTTP client."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None

    # ── KnowledgeBackend Protocol ───────────────────────────────────────

    def search_candidates(
        self, query: str, *, scope: str = "all", limit: int = 20
    ) -> list[Any]:
        """Forward candidate search to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/candidates"
        body: dict[str, Any] = {"query": query, "scope": scope, "limit": limit}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def disambiguate(self, candidates: list[Any], query: str) -> list[Any]:
        """Forward disambiguation to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/disambiguate"
        body: dict[str, Any] = {"candidates": candidates, "query": query}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def prepare_clarification(
        self, query: str, slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Forward clarification preparation to remote service."""
        return {}

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:
        """Forward clarification finalization to remote service."""
        return {}

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Remote knowledge is read-only — term sync is not supported."""
        _ = entity_code, entity_name, entity_source, fields, backfill_vectors
        logger.debug("Remote knowledge: sync_terms skipped (read-only)")

    def remove_terms(self, entity_code: str) -> None:
        """Remote knowledge is read-only — term removal is not supported."""
        _ = entity_code
        logger.debug("Remote knowledge: remove_terms skipped (read-only)")

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Remote knowledge does not support per-term lookup."""
        return None

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Remote knowledge does not support existence checks."""
        return False

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Remote knowledge does not support batch lookup."""
        return {}

    def get_type_codes_by_category(self, categories: list[int]) -> list[str]:
        """Remote knowledge does not support category lookup."""
        return []

    def embed(self, text: str) -> list[float]:
        """Remote knowledge does not support local embedding."""
        return [0.0] * 768

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Remote knowledge does not support local embedding."""
        return [[0.0] * 768 for _ in texts]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Forward embedding search to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/by-embedding"
        body: dict[str, Any] = {
            "vector": vector,
            "termTypes": term_types,
            "limit": limit,
        }
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def resolve_dimension_value(self, value_term_id: str) -> Any:
        """Remote knowledge does not support dimension resolution."""
        from datacloud_platform.models.shared import DimensionProperty

        return DimensionProperty(property_code="", object_code="")

    def get_referenced_by(self, value_term_id: str) -> list[Any]:
        """Remote knowledge does not support reference lookup."""
        return []

    def resolve_object_for_property(self, property_code: str) -> str | None:
        """Remote knowledge does not support property resolution."""
        return None

    def search_ontology(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Forward ontology search to remote service (no caching — real-time)."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/ontology"
        body: dict[str, Any] = {
            "keyword": keyword,
            "sceneId": scene_id,
            "queryType": query_type,
            "searchScope": search_scope,
            "pageSize": kwargs.get("page_size", 20),
            "resultPerType": kwargs.get("result_per_type", 5),
        }
        if "object_code" in kwargs:
            body["objectCode"] = kwargs["object_code"]
        if "view_code" in kwargs:
            body["viewCode"] = kwargs["view_code"]
        if "property_code" in kwargs:
            body["propertyCode"] = kwargs["property_code"]
        if "page_token" in kwargs:
            body["pageToken"] = kwargs["page_token"]
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def graph_query(
        self,
        base_id: str,
        scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict[str, Any]:
        """Remote knowledge does not support graph queries — returns empty."""
        _ = base_id, scene_id, object_code, match_by, values, step
        return {"nodes": [], "edges": []}

    def update_scores(self, records: list[Any]) -> None:
        """Remote knowledge does not support score updates."""
        _ = records
        logger.debug("Remote knowledge: update_scores skipped (read-only)")

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Remote knowledge does not support instance search — returns empty."""
        _ = base_id, object_code, select, where
        logger.debug("Remote knowledge: search_instances skipped (not supported)")
        return {"data": [], "totalCount": 0}

    def graph_path(
        self,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Remote knowledge does not support graph path — returns empty."""
        _ = base_id, scene_id, match_by, start_node, end_node, direction
        logger.debug("Remote knowledge: graph_path skipped (not supported)")
        return {"path": [], "edges": [], "hops": -1}
