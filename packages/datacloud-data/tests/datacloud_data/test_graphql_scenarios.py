"""GraphQL 场景测试：DB list、API action 真实执行。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_data_sdk.graphql.server import get_graphql_router
from datacloud_data_sdk.ontology.loader import OntologyLoader
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_graphql_db_list_returns_records(scenario_db_linked_with_data) -> None:
    """使用 scenario_db_linked fixture，创建独立 FastAPI app，挂载 GraphQL router，断言 customer_list 返回非空。"""
    loader, ds_manager = scenario_db_linked_with_data
    router = get_graphql_router(loader, ds_manager)
    app = FastAPI()
    app.include_router(router, prefix="/graphql")
    client = TestClient(app)
    resp = client.post("/graphql/", json={"query": "{ customerList { id name } }"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["data"] is not None
    records = data["data"]["customerList"]
    assert isinstance(records, list)
    assert len(records) > 0
    assert any(r.get("name") == "c1" for r in records)


@pytest.mark.asyncio
async def test_graphql_api_action_returns_records(load_scenario_api_linked: OntologyLoader) -> None:
    """加载 scenario_api_linked，mock httpx 对 /api/v1/customers 和 /api/v1/opportunities 的响应，调用 GraphQL query_customers 或 query_opportunities_by_customer，断言返回非空。"""
    loader = load_scenario_api_linked

    def make_mock_response(url: str):
        resp = MagicMock()
        resp.status_code = 200
        if "/customers" in url:
            resp.json.return_value = {"customers": [{"customer_id": "c1"}]}
        elif "/opportunities" in url:
            resp.json.return_value = {
                "opportunities": [
                    {"id": 1, "amount": 100.0, "customer_id": "c1"},
                    {"id": 2, "amount": 200.0, "customer_id": "c1"},
                ]
            }
        else:
            resp.json.return_value = {}
        resp.text = ""
        return resp

    async def mock_post(url, **kwargs):
        return make_mock_response(url)

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(side_effect=mock_post)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_instance

        router = get_graphql_router(loader)
        app = FastAPI()
        app.include_router(router, prefix="/graphql")
        client = TestClient(app)

        resp = client.post("/graphql/", json={"query": "{ queryCustomers { customerId } }"})
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data and data["data"] is not None
        records = data["data"]["queryCustomers"]
        assert isinstance(records, list) and len(records) > 0

        resp2 = client.post(
            "/graphql/",
            json={
                "query": 'query { queryOpportunitiesByCustomer(customerId: "c1") { id amount customerId } }'
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "data" in data2 and data2["data"] is not None
        records2 = data2["data"]["queryOpportunitiesByCustomer"]
        assert isinstance(records2, list) and len(records2) > 0


@pytest.mark.asyncio
async def test_graphql_linked_returns_nested(scenario_db_linked_with_data) -> None:
    """DB 同源 linked：customer_list { id, opportunities { id } } 返回嵌套商机。"""
    loader, ds_manager = scenario_db_linked_with_data
    router = get_graphql_router(loader, ds_manager)
    app = FastAPI()
    app.include_router(router, prefix="/graphql")
    client = TestClient(app)
    resp = client.post(
        "/graphql/",
        json={"query": "{ customerList { id name customerId opportunities { id amount } } }"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data and data["data"] is not None
    records = data["data"]["customerList"]
    assert isinstance(records, list) and len(records) > 0
    for r in records:
        assert "opportunities" in r
        opps = r["opportunities"]
        assert isinstance(opps, list)
        for o in opps:
            assert "id" in o and "amount" in o
    c1 = next(r for r in records if r.get("name") == "c1")
    assert len(c1["opportunities"]) == 2
    c2 = next(r for r in records if r.get("name") == "c2")
    assert len(c2["opportunities"]) == 1


@pytest.mark.asyncio
async def test_graphql_derived_returns_computed(scenario_db_derived_with_data) -> None:
    """DB derived expression + aggregation：sales_bo_list discount_amount，customer_list opportunity_count。"""
    loader, ds_manager = scenario_db_derived_with_data
    router = get_graphql_router(loader, ds_manager)
    app = FastAPI()
    app.include_router(router, prefix="/graphql")
    client = TestClient(app)
    resp = client.post(
        "/graphql/",
        json={"query": "{ salesBoList { id amount discountAmount } }"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data and data["data"] is not None
    records = data["data"]["salesBoList"]
    assert isinstance(records, list) and len(records) > 0
    for r in records:
        assert "discountAmount" in r
        amount = r.get("amount")
        expected = amount * 0.9 if amount is not None else None
        assert r["discountAmount"] == expected

    resp2 = client.post(
        "/graphql/",
        json={"query": "{ customerList { id name opportunityCount } }"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert "data" in data2 and data2["data"] is not None
    records2 = data2["data"]["customerList"]
    assert isinstance(records2, list) and len(records2) > 0
    for r in records2:
        assert "opportunityCount" in r
    c1 = next(r for r in records2 if r.get("name") == "c1")
    assert c1["opportunityCount"] == 2
    c2 = next(r for r in records2 if r.get("name") == "c2")
    assert c2["opportunityCount"] == 1
