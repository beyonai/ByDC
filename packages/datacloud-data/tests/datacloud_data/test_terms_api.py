from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_platform.api.routers.terms_routes import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _TermLoader:
    def __init__(self) -> None:
        self.last_page_args: dict[str, Any] = {}

    def get_entries_page(
        self,
        term_set: str,
        dataset_id: int | None = None,
        library_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        self.last_page_args = {
            "term_set": term_set,
            "dataset_id": dataset_id,
            "library_id": library_id,
            "term_type_code": term_type_code,
            "keyword": keyword,
            "limit": limit,
            "offset": offset,
        }
        entries = [
            {"code": "TODO", "label": "待启用"},
            {"code": "ENABLED", "label": "启用", "metadata": {"enabled": True}},
            {"code": "DISABLED", "label": "停用"},
        ]
        return entries[offset : offset + limit], len(entries)


def _client() -> tuple[TestClient, _TermLoader]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    loader = OntologyLoader()
    term_loader = _TermLoader()
    loader.configure(term_loader=term_loader)
    app.state.loader = loader
    return TestClient(app), term_loader


def test_term_options_endpoint_returns_paginated_options() -> None:
    client, term_loader = _client()
    response = client.post(
        "/api/datacloud/terms/options",
        json={
            "termSet": "status.code",
            "termTypeCode": "status",
            "datasetId": 100,
            "keyword": "启",
            "page": 1,
            "pageSize": 2,
        },
    )

    assert response.status_code == 200
    assert term_loader.last_page_args == {
        "term_set": "status.code",
        "dataset_id": 100,
        "library_id": None,
        "term_type_code": "status",
        "keyword": "启",
        "limit": 2,
        "offset": 0,
    }
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["total"] == 3
    assert payload["data"]["hasMore"] is True
    assert payload["data"]["items"] == [
        {"label": "待启用", "value": "TODO", "code": "TODO", "name": "待启用", "metadata": {}},
        {
            "label": "启用",
            "value": "ENABLED",
            "code": "ENABLED",
            "name": "启用",
            "metadata": {"enabled": True},
        },
    ]


def test_term_options_endpoint_returns_name_value_when_requested() -> None:
    client, _term_loader = _client()
    response = client.post(
        "/api/datacloud/terms/options",
        json={
            "termSet": "status.code",
            "termTypeCode": "status",
            "termField": "name",
            "datasetId": 100,
            "keyword": "启",
            "page": 1,
            "pageSize": 1,
        },
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["value"] == "待启用"


def test_term_options_endpoint_validates_required_term_set() -> None:
    client, _term_loader = _client()
    response = client.post(
        "/api/datacloud/terms/options",
        json={"termTypeCode": "status"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "message": "termSet is required",
        "data": None,
    }
