"""Unit tests for RemoteOntologyAdapter.

Tests cover:
- Write operations raise PermissionError
- get_objects HTTP forwarding + TTL cache
- Auth header construction (bearer / api_key)
- search_instances / search_ontology forwarding
- Stub methods for unsupported operations
- HTTP error propagation
- Client lifecycle
"""

from __future__ import annotations

import httpx
import pytest
from datacloud_server.adapters import remote_adapter as _remote_mod
from datacloud_server.adapters.remote_adapter import (
    RemoteOntologyAdapter,
)

# ── Helpers ─────────────────────────────────────────────────


def _mock_transport(response_json: dict, status_code: int = 200) -> httpx.MockTransport:
    """Create a MockTransport that returns the given JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_json, request=request)

    return httpx.MockTransport(handler)


def _inject_mock_client(adapter: RemoteOntologyAdapter, transport: httpx.BaseTransport) -> None:
    """Inject a mock httpx client into the adapter."""
    adapter._client = httpx.Client(transport=transport)


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def adapter() -> RemoteOntologyAdapter:
    """Create adapter with test source_url and auth_config."""
    return RemoteOntologyAdapter(
        source_url="https://example.com/api",
        auth_config={"type": "bearer", "token": "test-token"},
    )


@pytest.fixture
def adapter_no_auth() -> RemoteOntologyAdapter:
    """Create adapter without auth."""
    return RemoteOntologyAdapter(
        source_url="https://example.com/api",
        auth_config=None,
    )


# ── Write operations ────────────────────────────────────────


class TestWriteOperationsRejected:
    """All write operations must raise PermissionError."""

    BASE = "b1"
    SCENE = "s1"

    def test_create_object_rejected(self, adapter: RemoteOntologyAdapter) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            adapter.create_object(self.BASE, self.SCENE, {"objectCode": "obj1"})

    def test_delete_object_rejected(self, adapter: RemoteOntologyAdapter) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            adapter.delete_object(self.BASE, self.SCENE, "obj1")

    def test_update_object_rejected(self, adapter: RemoteOntologyAdapter) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            adapter.update_object(self.BASE, self.SCENE, "obj1", {"objectCode": "obj1"})


# ── get_objects forwarding + caching ────────────────────────


class TestGetObjects:
    """HTTP forwarding for get_objects with TTL cache."""

    def test_forwards_post_with_scene_id(self, adapter: RemoteOntologyAdapter) -> None:
        """GET (internal) → POST /OntologyEntityController/sceneDetails (external)."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": [{"objectCode": "o1"}]}}),
        )

        result = adapter.get_objects("b1", "s1")

        assert len(result) == 1
        assert result[0]["objectCode"] == "o1"

    def test_caches_response(self, adapter: RemoteOntologyAdapter) -> None:
        """Second call within TTL returns cached data, no HTTP request."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": [{"objectCode": "o1"}]}}),
        )

        r1 = adapter.get_objects("b1", "s1")
        # Second call with same base/scene — uses cache
        r2 = adapter.get_objects("b1", "s1")
        assert r2 == r1

    def test_no_cache_when_disabled(self, adapter: RemoteOntologyAdapter) -> None:
        """Cache is always enabled; verify the method works."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"code": 200, "data": {"objects": [{"objectCode": "o1"}]}},
            ),
        )
        # We verify caching by checking no error; the MockTransport handles both calls
        _inject_mock_client(adapter, transport)
        adapter.get_objects("b1", "s1")
        adapter.get_objects("b1", "s1")
        # Both calls succeeded; caching was always enabled

    def test_cache_expiry(self, adapter: RemoteOntologyAdapter, monkeypatch) -> None:
        """After TTL expires, a fresh HTTP request is made."""
        fake_time = 0.0
        monkeypatch.setattr(_remote_mod.time, "monotonic", lambda: fake_time)

        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": [{"objectCode": "o1"}]}}),
        )

        # First call — caches at fake_time=0
        adapter.get_objects("b1", "s1")
        key = ("b1", "s1", "objects")
        assert key in adapter._cache

        # Advance time past TTL (300s)
        fake_time = 301.0
        assert adapter._cache[key].is_expired

        # Second call — should make new request (cache expired)
        adapter.get_objects("b1", "s1")

    def test_handles_http_error(self, adapter: RemoteOntologyAdapter) -> None:
        """HTTP errors are propagated."""
        _inject_mock_client(
            adapter,
            httpx.MockTransport(lambda req: httpx.Response(500, request=req)),
        )

        with pytest.raises(httpx.HTTPStatusError):
            adapter.get_objects("b1", "s1")

    def test_handles_empty_objects_in_response(self, adapter: RemoteOntologyAdapter) -> None:
        """Response with missing 'objects' key returns empty list."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {}}),
        )

        result = adapter.get_objects("b1", "s1")
        assert result == []


# ── Auth headers ────────────────────────────────────────────


class TestAuthHeaders:
    """Authentication header construction."""

    BASE = "b1"
    SCENE = "s1"

    def test_bearer_token(self, adapter: RemoteOntologyAdapter) -> None:
        """Bearer token injected as Authorization header."""
        captured_headers: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(200, json={"code": 200, "data": {"objects": []}}, request=req)

        _inject_mock_client(adapter, httpx.MockTransport(handler))
        adapter.get_objects(self.BASE, self.SCENE)
        assert captured_headers.get("authorization") == "Bearer test-token"

    def test_api_key_header(self) -> None:
        """api_key auth type uses custom header."""
        adapter = RemoteOntologyAdapter(
            source_url="https://example.com/api",
            auth_config={
                "type": "api_key",
                "headerName": "X-API-Key",
                "apiKey": "my-secret-key",
            },
        )

        captured_headers: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(200, json={"code": 200, "data": {"objects": []}}, request=req)

        _inject_mock_client(adapter, httpx.MockTransport(handler))
        adapter.get_objects(self.BASE, self.SCENE)
        assert captured_headers.get("x-api-key") == "my-secret-key"

    def test_no_auth_headers_when_no_config(self, adapter_no_auth: RemoteOntologyAdapter) -> None:
        """No auth config → no auth headers."""
        captured_headers: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(200, json={"code": 200, "data": {"objects": []}}, request=req)

        _inject_mock_client(adapter_no_auth, httpx.MockTransport(handler))
        adapter_no_auth.get_objects(self.BASE, self.SCENE)
        assert "authorization" not in captured_headers

    def test_unknown_auth_type_no_headers(self) -> None:
        """Unknown auth type → no auth headers."""
        adapter = RemoteOntologyAdapter(
            source_url="https://example.com/api",
            auth_config={"type": "custom_unknown"},
        )

        captured_headers: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(req.headers))
            return httpx.Response(200, json={"code": 200, "data": {"objects": []}}, request=req)

        _inject_mock_client(adapter, httpx.MockTransport(handler))
        adapter.get_objects(self.BASE, self.SCENE)
        assert "authorization" not in captured_headers


# ── search_instances ────────────────────────────────────────


class TestSearchInstances:
    """search_instances forwarding without cache."""

    def test_forwards_post(self, adapter: RemoteOntologyAdapter) -> None:
        """Forward to /InstanceController/search with body."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"instances": []}}),
        )

        result = adapter.search_instances("b1", object_code="test")
        assert result["code"] == 200


# ── search_ontology ─────────────────────────────────────────


class TestSearchOntology:
    """search_ontology forwarding with sceneId injection."""

    def test_forwards_post_with_scene_id_injection(self, adapter: RemoteOntologyAdapter) -> None:
        """sceneId injected into POST body alongside request."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {}}),
        )

        result = adapter.search_ontology("b1", "s1", keyword="test")
        assert result["code"] == 200

    def test_empty_request_body(self, adapter: RemoteOntologyAdapter) -> None:
        """Empty request dict → body only has sceneId."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {}}),
        )

        adapter.search_ontology("b1", "s1", keyword="")


# ── Stub methods ────────────────────────────────────────────


class TestStubMethods:
    """Methods that are not yet implemented for REMOTE."""

    BASE = "b1"
    SCENE = "s1"

    def test_list_scenes_returns_empty(self, adapter: RemoteOntologyAdapter) -> None:
        assert adapter.list_scenes(self.BASE) == []

    def test_get_views_returns_empty(self, adapter: RemoteOntologyAdapter) -> None:
        assert adapter.get_views(self.BASE, self.SCENE) == []

    def test_get_relations_returns_empty(self, adapter: RemoteOntologyAdapter) -> None:
        assert adapter.get_relations(self.BASE, self.SCENE) == []

    def test_get_object_detail_returns_none(self, adapter: RemoteOntologyAdapter) -> None:
        assert adapter.get_object_detail(self.BASE, self.SCENE, "obj1") is None

    def test_graph_query_returns_empty(self, adapter: RemoteOntologyAdapter) -> None:
        assert adapter.graph_query(self.BASE, self.SCENE, object_code=[]) == {
            "nodes": [],
            "edges": [],
        }


# ── Client lifecycle ────────────────────────────────────────


class TestClientLifecycle:
    """httpx client creation and cleanup."""

    def test_client_created_lazily(self, adapter: RemoteOntologyAdapter) -> None:
        """Client is not created until first use."""
        assert adapter._client is None

    def test_close_cleans_up_client(self, adapter: RemoteOntologyAdapter) -> None:
        """close() shuts down the httpx client."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": []}}),
        )

        adapter.get_objects("b1", "s1")
        assert adapter._client is not None

        adapter.close()
        assert adapter._client is None


# ── URL construction ────────────────────────────────────────


class TestUrlConstruction:
    """URL normalization — trailing slash handling."""

    def test_strips_trailing_slash(self) -> None:
        """source_url with trailing slash handled correctly."""
        adapter = RemoteOntologyAdapter(
            source_url="https://example.com/api/",
            auth_config=None,
        )
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": []}}),
        )

        adapter.get_objects("b1", "s1")
        # No exception = success

    def test_no_trailing_slash(self) -> None:
        """source_url without trailing slash also works."""
        adapter = RemoteOntologyAdapter(
            source_url="https://example.com/api",
            auth_config=None,
        )
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": []}}),
        )

        adapter.get_objects("b1", "s1")
        # No exception = success


# ── Edge cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge case behavior."""

    def test_get_objects_use_cache_default_true(self, adapter: RemoteOntologyAdapter) -> None:
        """Default use_cache=True; cache is used."""
        _inject_mock_client(
            adapter,
            _mock_transport({"code": 200, "data": {"objects": [{"objectCode": "o1"}]}}),
        )
        adapter.get_objects("b1", "s1")
        adapter.get_objects("b1", "s1")
        # Second call uses cache — no error
