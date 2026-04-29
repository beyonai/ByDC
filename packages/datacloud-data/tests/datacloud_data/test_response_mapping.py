"""Tests for response_mapping."""

from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path


def test_extract_normal() -> None:
    data = {
        "response": {
            "users": [
                {"userId": "u1", "userName": "Alice", "orgId": "o1"},
                {"userId": "u2", "userName": "Bob", "orgId": "o2"},
            ]
        }
    }
    output_params = [
        ("userId", "$.response.users[].userId"),
        ("userName", "$.response.users[].userName"),
        ("orgId", "$.response.users[].orgId"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert len(records) == 2
    assert records[0] == {"userId": "u1", "userName": "Alice", "orgId": "o1"}
    assert records[1] == {"userId": "u2", "userName": "Bob", "orgId": "o2"}


def test_extract_empty_array() -> None:
    data = {"response": {"users": []}}
    output_params = [
        ("userId", "$.response.users[].userId"),
        ("userName", "$.response.users[].userName"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert records == []


def test_extract_path_not_exists() -> None:
    data = {"response": {}}
    output_params = [
        ("userId", "$.response.users[].userId"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert records == []


def test_extract_invalid_mapping_path() -> None:
    data = {"response": {"users": [{"userId": "u1"}]}}
    output_params = [
        ("userId", "invalid_path"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert records == []


def test_extract_root_object_fields() -> None:
    data = {"todoId": "1777010261647865", "status": "Received"}
    output_params = [
        ("todoId", "$.todoId"),
        ("status", "$.status"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert records == [{"todoId": "1777010261647865", "status": "Received"}]


def test_extract_nested_fields_in_array_items() -> None:
    data = {
        "response": {
            "users": [
                {"profile": {"userId": "u1", "userName": "Alice"}},
                {"profile": {"userId": "u2", "userName": "Bob"}},
            ]
        }
    }
    output_params = [
        ("userId", "$.response.users[].profile.userId"),
        ("userName", "$.response.users[].profile.userName"),
    ]
    records = extract_by_mapping_path(data, output_params)
    assert records == [
        {"userId": "u1", "userName": "Alice"},
        {"userId": "u2", "userName": "Bob"},
    ]


def test_extract_mixed_root_fields_and_rows_array() -> None:
    data = {
        "total": 75,
        "rows": [
            {
                "id": 75,
                "projectCode": "PROJ00000055",
                "taskName": "福州银行BI故障分析",
            }
        ],
        "code": 0,
        "msg": None,
    }
    output_params = [
        ("code", "$.code"),
        ("msg", "$.msg"),
        ("total", "$.total"),
        ("id", "$.rows[].id"),
        ("projectCode", "$.rows[].projectCode"),
        ("taskName", "$.rows[].taskName"),
    ]

    records = extract_by_mapping_path(data, output_params)

    assert records == [
        {
            "code": 0,
            "msg": None,
            "total": 75,
            "id": 75,
            "projectCode": "PROJ00000055",
            "taskName": "福州银行BI故障分析",
        }
    ]
