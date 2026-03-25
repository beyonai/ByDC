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
