import pytest


@pytest.mark.type3_api
def test_expense_apply_and_list_flow(api_client) -> None:
    """费用报备：先申请，再查询、修改、审核的一条完整流程。"""
    pytest.importorskip("httpx")
    client = api_client

    # 1. 先申请一条费用报备
    apply_body = {
        "applicantEmpNo": "0000000001",
        "applicantName": "王小明",
        "applicantOrgId": "6978",
        "expenseAmount": 1234.5,
        "expenseDesc": "pytest expense apply",
    }
    resp_apply = client.post("/api/v1/expense-reports", json=apply_body)
    assert resp_apply.status_code == 200
    body_apply = resp_apply.json()
    expense_id = body_apply.get("id")
    assert expense_id, f"apply response should contain id, got: {body_apply}"

    # 2. 通过列表接口按申请人工号查询，能查到刚刚创建的记录
    resp_list = client.post(
        "/api/v1/expense-reports/list",
        json={"applicantEmpNos": [apply_body["applicantEmpNo"]]},
    )
    print("LIST STATUS:", resp_list.status_code, resp_list.json())
    assert resp_list.status_code == 200
    body_list = resp_list.json()
    assert isinstance(body_list, dict)
    assert "expenseReports" in body_list
    reports = body_list["expenseReports"]
    assert isinstance(reports, list) and reports, body_list
    ids = {str(r.get("id")) for r in reports}
    assert str(expense_id) in ids

    # 3. 修改这条费用报备的金额和备注
    update_body = {
        "id": str(expense_id),
        "expenseAmount": 1500.0,
        "expenseDesc": "pytest expense updated",
    }
    resp_update = client.post("/api/v1/expense-reports/update", json=update_body)
    assert resp_update.status_code == 200
    body_update = resp_update.json()
    assert body_update.get("id") == str(expense_id)

    # 4. 发起批量审批，通过这条费用报备
    approve_body = {
        "expenseReportIds": [str(expense_id)],
        "approvalStatus": "Approving",
        "approvalComment": "approved by pytest",
    }
    resp_approve = client.post(
        "/api/v1/expense-reports/batch/approve",
        json=approve_body,
    )
    assert resp_approve.status_code == 200
    body_approve = resp_approve.json()
    assert body_approve.get("approvalStatus") in ("APPROVED", "PENDING")


@pytest.mark.type3_api
def test_expense_basic_endpoints_available(api_client) -> None:
    """费用报备主要接口存在且不会 5xx 的冒烟测试。"""
    pytest.importorskip("httpx")
    client = api_client

    # list 支持默认请求体
    resp_list = client.post("/api/v1/expense-reports/list", json={})
    assert resp_list.status_code < 500
    _ = resp_list.json()

    # 其它接口：形状合法的 body + 非 5xx 检查
    cases = [
        ("/api/v1/expense-reports/update", {"id": "0"}),
        (
            "/api/v1/expense-reports/batch/approve",
            {"expenseReportIds": [], "approvalStatus": "Approving"},
        ),
    ]
    for path, payload in cases:
        r = client.post(path, json=payload)
        assert r.status_code < 500, f"{path} returns 5xx: {r.status_code} {r.text}"
        _ = r.json()

