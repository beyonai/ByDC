import uuid

import pytest


@pytest.mark.type3_api
def test_todo_full_flow(api_client) -> None:
    """从创建待办到查询、接收、处理、审批的完整流程冒烟测试。"""
    pytest.importorskip("httpx")
    client = api_client

    promoter_code = "promoter1"
    handler_code = "handler1"
    headers_promoter = {"X-User-Code": promoter_code}
    headers_handler = {"X-User-Code": handler_code}

    # 1. 创建待办
    unique_title = f"pytest-todo-{uuid.uuid4()}"
    create_body = {
        "title": unique_title,
        "promoter": promoter_code,
        "handlerIds": [handler_code],
        "content": "pytest create todo flow",
    }

    resp_create = client.post("/api/v1/todos", json=create_body, headers=headers_promoter)
    assert resp_create.status_code < 500
    body_create = resp_create.json()
    todo_id = body_create.get("todoId")
    assert todo_id, f"create response should contain todoId, got: {body_create}"

    # 2. 列表查询中能查到刚刚创建的待办
    list_body = {
        "keyword": unique_title,
    }
    resp_list = client.post("/api/v1/todos/list", json=list_body, headers=headers_promoter)
    assert resp_list.status_code == 200
    body_list = resp_list.json()
    assert isinstance(body_list, dict)
    assert "data" in body_list
    assert isinstance(body_list["data"], list)

    matched = [
        item
        for item in body_list["data"]
        if str(item.get("todoId")) == str(todo_id) or item.get("title") == unique_title
    ]
    assert matched, f"created todo not found in list, list body: {body_list}"

    # 3. 处理人接收待办
    accept_body = {
        "todoId": str(todo_id),
    }
    resp_accept = client.post("/api/v1/todos/accept", json=accept_body, headers=headers_handler)
    assert resp_accept.status_code == 200
    body_accept = resp_accept.json()
    assert isinstance(body_accept, dict)
    assert body_accept.get("todoId") == str(todo_id)

    # 4. 处理人将待办进度更新为 100%，触发待审核状态
    process_body = {
        "todoIds": [str(todo_id)],
        "handleComment": "done by pytest",
        "progress": 100,
    }
    resp_process = client.post(
        "/api/v1/todos/batch/process",
        json=process_body,
        headers=headers_handler,
    )
    assert resp_process.status_code == 200
    body_process = resp_process.json()
    assert isinstance(body_process, dict)
    assert str(todo_id) in body_process.get("handledIds", [])

    # 5. 发起人审批待办（通过）
    approve_body = {
        "todoIds": [str(todo_id)],
        "approvalStatus": "Approving",
        "approvalComment": "approved by pytest",
    }
    resp_approve = client.post(
        "/api/v1/todos/batch/approve",
        json=approve_body,
        headers=headers_promoter,
    )
    assert resp_approve.status_code == 200
    body_approve = resp_approve.json()
    assert isinstance(body_approve, dict)
    assert str(todo_id) in body_approve.get("handledIds", [])


@pytest.mark.type3_api
def test_todos_basic_endpoints_available(api_client) -> None:
    """待办主要接口存在且不会 5xx 的冒烟测试。"""
    pytest.importorskip("httpx")
    client = api_client

    # list 支持默认请求体
    resp_list = client.post("/api/v1/todos/list", json={})
    assert resp_list.status_code < 500
    assert isinstance(resp_list.json(), dict)

    # 其它主要接口做形状合法的请求体 + 非 5xx 检查
    cases = [
        ("/api/v1/todos/batch", {"todoIds": []}),
        ("/api/v1/todos/batch/urge", {"todoIds": []}),
        ("/api/v1/todos/batch/process", {"todoIds": []}),
        ("/api/v1/todos/update", {"todoId": "0"}),
        ("/api/v1/todos/batch/approve", {"todoIds": [], "approvalStatus": "Approving"}),
    ]

    for path, payload in cases:
        r = client.post(path, json=payload)
        assert r.status_code < 500, f"{path} returns 5xx: {r.status_code} {r.text}"
        # 响应至少应该是 JSON
        _ = r.json()

