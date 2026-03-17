"""GraphQL where 参数到 filters 格式转换的测试。"""

import pytest

from datacloud_data.graphql.arg_converter import where_to_filters


def test_where_to_filters_converts_eq() -> None:
    """where={"status": {"eq": "ACTIVE"}} -> {"status": {"op": "eq", "value": "ACTIVE"}}"""
    where = {"status": {"eq": "ACTIVE"}}
    assert where_to_filters(where) == {"status": {"op": "eq", "value": "ACTIVE"}}


def test_where_to_filters_converts_gte() -> None:
    """where={"amount": {"gte": 100}} -> {"amount": {"op": "gte", "value": 100}}"""
    where = {"amount": {"gte": 100}}
    assert where_to_filters(where) == {"amount": {"op": "gte", "value": 100}}


def test_where_to_filters_converts_in() -> None:
    """where={"status": {"in": ["A", "B"]}} -> {"status": {"op": "in", "value": ["A", "B"]}}"""
    where = {"status": {"in": ["A", "B"]}}
    assert where_to_filters(where) == {"status": {"op": "in", "value": ["A", "B"]}}


def test_where_to_filters_converts_gt() -> None:
    """where={"amount": {"gt": 50}} -> {"amount": {"op": "gt", "value": 50}}"""
    where = {"amount": {"gt": 50}}
    assert where_to_filters(where) == {"amount": {"op": "gt", "value": 50}}


def test_where_to_filters_converts_lt() -> None:
    """where={"amount": {"lt": 200}} -> {"amount": {"op": "lt", "value": 200}}"""
    where = {"amount": {"lt": 200}}
    assert where_to_filters(where) == {"amount": {"op": "lt", "value": 200}}


def test_where_to_filters_converts_lte() -> None:
    """where={"amount": {"lte": 100}} -> {"amount": {"op": "lte", "value": 100}}"""
    where = {"amount": {"lte": 100}}
    assert where_to_filters(where) == {"amount": {"op": "lte", "value": 100}}


def test_where_to_filters_converts_like() -> None:
    """where={"name": {"like": "%foo%"}} -> {"name": {"op": "like", "value": "%foo%"}}"""
    where = {"name": {"like": "%foo%"}}
    assert where_to_filters(where) == {"name": {"op": "like", "value": "%foo%"}}


def test_where_to_filters_converts_is_null() -> None:
    """where={"deleted_at": {"is_null": True}} -> {"deleted_at": {"op": "is_null"}}"""
    where = {"deleted_at": {"is_null": True}}
    assert where_to_filters(where) == {"deleted_at": {"op": "is_null"}}


def test_where_to_filters_converts_is_not_null() -> None:
    """where={"updated_at": {"is_not_null": True}} -> {"updated_at": {"op": "is_not_null"}}"""
    where = {"updated_at": {"is_not_null": True}}
    assert where_to_filters(where) == {"updated_at": {"op": "is_not_null"}}


def test_where_to_filters_converts_neq() -> None:
    """where={"status": {"neq": "DELETED"}} -> {"status": {"op": "neq", "value": "DELETED"}}"""
    where = {"status": {"neq": "DELETED"}}
    assert where_to_filters(where) == {"status": {"op": "neq", "value": "DELETED"}}


def test_where_to_filters_empty_where_returns_empty_dict() -> None:
    """空 where 返回 {}"""
    assert where_to_filters({}) == {}


def test_where_to_filters_none_returns_empty_dict() -> None:
    """None where 返回 {}"""
    assert where_to_filters(None) == {}


def test_where_to_filters_combined_conditions() -> None:
    """多字段组合：status eq + amount gte"""
    where = {"status": {"eq": "ACTIVE"}, "amount": {"gte": 100}}
    assert where_to_filters(where) == {
        "status": {"op": "eq", "value": "ACTIVE"},
        "amount": {"op": "gte", "value": 100},
    }
