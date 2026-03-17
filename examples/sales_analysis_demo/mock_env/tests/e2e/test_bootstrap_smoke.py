"""E2E smoke checks for bootstrap assets and api entry."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_bootstrap_assets_and_api_smoke(ddl_sql_path, resource_data_dir, resource_knowledge_dir) -> None:
    assert ddl_sql_path.exists()
    assert resource_data_dir.exists()
    assert resource_knowledge_dir.exists()

    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from sales_analysis_demo.main import app

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
