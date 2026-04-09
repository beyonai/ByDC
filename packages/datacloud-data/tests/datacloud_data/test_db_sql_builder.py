"""Tests for db_sql_builder."""

import pytest

from datacloud_data_sdk.executor.db_sql_builder import build_select_sql, build_where_clause


def test_build_where_from_filters() -> None:
    filters = {
        "status": {"op": "eq", "value": "ACTIVE"},
        "amount": {"op": "gte", "value": 100},
    }
    field_to_col = {"status": "status", "amount": "amount"}
    sql, params = build_where_clause(filters, field_to_col)
    assert "status" in sql and "amount" in sql
    assert params.get("p_status") == "ACTIVE"
    assert params.get("p_amount") == 100


def test_build_where_empty_filters() -> None:
    sql, params = build_where_clause({}, {"a": "a"})
    assert sql == ""
    assert params == {}


def test_build_select_no_aggregates() -> None:
    fields = [("id", "id"), ("name", "name")]
    field_to_col = {"id": "id", "name": "name"}
    sql, col_keys = build_select_sql(
        table="t1",
        fields=fields,
        aggregates=None,
        group_by=None,
        where_sql="",
        db_type="POSTGRESQL",
        field_to_col=field_to_col,
    )
    assert "SELECT" in sql and "t1" in sql
    assert col_keys == ["id", "name"]


def test_build_select_aggregates_only() -> None:
    agg = [{"field": "amount", "func": "sum", "as": "总金额"}]
    field_to_col = {"amount": "amount"}
    sql, col_keys = build_select_sql(
        table="t1",
        fields=[],
        aggregates=agg,
        group_by=None,
        where_sql="",
        db_type="POSTGRESQL",
        field_to_col=field_to_col,
    )
    assert "SUM" in sql and "总金额" in sql
    assert col_keys == ["总金额"]


def test_build_select_aggregates_with_group_by() -> None:
    agg = [{"field": "amount", "func": "sum", "as": "金额汇总"}]
    fields = [("region", "region")]
    field_to_col = {"region": "region", "amount": "amount"}
    sql, col_keys = build_select_sql(
        table="t1",
        fields=fields,
        aggregates=agg,
        group_by=["region"],
        where_sql="",
        db_type="POSTGRESQL",
        field_to_col=field_to_col,
    )
    assert "GROUP BY" in sql
    assert col_keys == ["region", "金额汇总"]


def test_build_select_sql_with_derived_expression() -> None:
    sql, col_keys = build_select_sql(
        table="sales_bo",
        fields=[("id", "id"), ("amount", "amount")],
        aggregates=None,
        group_by=None,
        where_sql="",
        db_type="SQLITE",
        field_to_col={"id": "id", "amount": "amount"},
        derived_expressions=[("discount_amount", "amount * 0.9")],
    )
    assert "discount_amount" in col_keys
    assert "amount * 0.9" in sql or "discount_amount" in sql


def test_build_select_sql_with_derived_aggregation() -> None:
    sql, col_keys = build_select_sql(
        table="customer",
        fields=[("id", "id"), ("customer_id", "customer_id")],
        derived_expressions=None,
        derived_aggregations=[
            {
                "alias": "opportunity_count",
                "target_table": "opportunity",
                "target_field": "id",
                "func": "count",
                "join_from": "customer_id",
                "join_to": "customer_id",
            }
        ],
        aggregates=None,
        group_by=None,
        where_sql="",
        db_type="SQLITE",
        field_to_col={"id": "id", "customer_id": "customer_id"},
    )
    assert "opportunity_count" in col_keys
    assert "opportunity" in sql and "COUNT" in sql.upper()


def test_build_select_sql_with_linked_joins() -> None:
    """linked_joins 生成 LEFT JOIN 与带前缀的 target 列。"""
    sql, col_keys = build_select_sql(
        table="customer",
        fields=[("id", "id"), ("name", "name"), ("customer_id", "customer_id")],
        aggregates=None,
        group_by=None,
        where_sql="",
        db_type="SQLITE",
        field_to_col={"id": "id", "name": "name", "customer_id": "customer_id"},
        linked_joins=[
            {
                "linked_field": "opportunities",
                "target_table": "opportunity",
                "join_from": "customer_id",
                "join_to": "customer_id",
                "target_fields": [("id", "id"), ("amount", "amount")],
            }
        ],
    )
    assert "opportunities_id" in col_keys
    assert "opportunities_amount" in col_keys
    assert "LEFT JOIN" in sql and "opportunity" in sql
    assert "opportunities_id" in sql or "opportunities_amount" in sql


def test_build_select_sql_with_limit_offset() -> None:
    sql, _ = build_select_sql(
        table="t",
        fields=[("id", "id")],
        aggregates=None,
        group_by=None,
        where_sql="",
        db_type="SQLITE",
        field_to_col={"id": "id"},
        limit=10,
        offset=5,
    )
    assert "LIMIT 10" in sql
    assert "OFFSET 5" in sql
