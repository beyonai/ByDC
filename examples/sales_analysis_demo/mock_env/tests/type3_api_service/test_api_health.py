"""Type3: tests for API availability from src service."""

from __future__ import annotations

import pytest


@pytest.mark.type3_api
def test_health_endpoint() -> None:
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from sales_analysis_demo.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


@pytest.mark.type3_api
def test_routes_endpoint() -> None:
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from sales_analysis_demo.main import app

    client = TestClient(app)
    resp = client.get("/api/routes")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert "routes" in body
