"""Remote adapter — HTTP-forwarding backends for remote ontology & knowledge services.

Refactored from datacloud_server/adapters/remote_adapter.py into two separate
Platform Backend classes: RemoteOntologyBackend (OntologyBackend Protocol) and
RemoteKnowledgeBackend (KnowledgeBackend Protocol).
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any

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
        from datacloud_platform.models import ParsedOwlContent

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

    def get_objects(self, loader: Any, base_id: str, scene_id: str) -> list[Any]:
        """Fetch objects from remote scene details endpoint.

        5-minute TTL cache on the response.
        """
        cache_key = f"objects:{base_id}:{scene_id}"
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired:
            return entry.data  # type: ignore[no-any-return]

        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/sceneDetails"
        response = client.post(url, json={"sceneId": scene_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        data = result.get("data", {}).get("objects", [])
        self._cache[cache_key] = _CacheEntry(data, ttl=300)
        return data  # type: ignore[no-any-return]

    def get_object_detail(self, loader: Any, object_code: str) -> Any | None:
        """Remote ontology does not support per-object detail."""
        return None


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
        return response.json()  # type: ignore[no-any-return]

    def disambiguate(self, candidates: list[Any], query: str) -> list[Any]:
        """Forward disambiguation to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/disambiguate"
        body: dict[str, Any] = {"candidates": candidates, "query": query}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

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
        return response.json()  # type: ignore[no-any-return]

    def resolve_dimension_value(self, value_term_id: str) -> Any:
        """Remote knowledge does not support dimension resolution."""
        from datacloud_platform.models import DimensionProperty

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
        return response.json()  # type: ignore[no-any-return]

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
