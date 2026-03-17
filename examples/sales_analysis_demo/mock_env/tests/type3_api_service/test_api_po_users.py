import pytest


@pytest.mark.type3_api
def test_po_users_query_by_user_code_uses_seed_data(api_client) -> None:
    """人员查询接口：使用 seed 数据中的 user_code，验证能查到对应人员。"""
    pytest.importorskip("httpx")
    client = api_client

    # 使用 mock 数据中的一个 user_code，例如 0000000001（王小明）
    resp = client.post(
        "/api/v1/po/users/query",
        json={"userIds": ["0027015006"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    users = body.get("users")
    assert isinstance(users, list) and users, body
    codes = {u.get("userCode") or u.get("user_code") for u in users}
    assert "0027015006" in codes


@pytest.mark.type3_api
def test_po_users_by_org_invalid_id_returns_empty(api_client) -> None:
    """按组织查人员：非法 orgId 返回空数组。"""
    pytest.importorskip("httpx")
    client = api_client

    resp = client.post(
        "/api/v1/po/users/by-org",
        json={"orgId": "not-int"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert body.get("users") == []

