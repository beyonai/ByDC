import pytest


@pytest.mark.type3_api
def test_po_orgs_query_by_ids_uses_seed_data(api_client) -> None:
    """组织查询接口：使用 seed 数据中的 orgId，验证能查到对应组织。"""
    pytest.importorskip("httpx")
    client = api_client

    # 使用 mock 数据里的真实 orgId 与名称，例如 7468 -> 云业务营销部
    resp = client.post(
        "/api/v1/po/organizations/query",
        json={"orgIds": ["7468"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    orgs = body.get("organizations")
    assert isinstance(orgs, list) and orgs, body
    ids = {o.get("org_id") for o in orgs}
    assert "7468" in ids


@pytest.mark.type3_api
def test_po_orgs_children_invalid_id_returns_empty(api_client) -> None:
    """下级组织查询：非法 orgId 返回空数组。"""
    pytest.importorskip("httpx")
    client = api_client

    resp = client.post(
        "/api/v1/po/organizations/children",
        json={"orgId": "not-int"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert body.get("organizations") == []

