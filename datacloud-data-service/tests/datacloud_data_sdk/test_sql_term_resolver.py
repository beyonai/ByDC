"""sql_term_resolver 模块测试。"""
from __future__ import annotations

import pytest

from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import (
    ObjectViewField,
    ObjectViewObject,
    ObjectViewPayload,
    ObjectViewSource,
)
from datacloud_data_sdk.plan.sql_term_resolver import resolve_sql_literals


def test_resolve_sql_literals_col_equals_value() -> None:
    """col = '待办' 替换为 col = 'TODO'。"""
    loader = TermLoader.from_mapping({
        "status.code": [
            {"code": "TODO", "label": "待办"},
            {"code": "DONE", "label": "已完成"},
        ],
    })
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="s1", source_type="DB", datasource_alias="ds1")],
        objects=[
            ObjectViewObject(
                object_id="o1",
                object_name="Sales",
                source_id="s1",
                table="sales_bo",
                fields=[
                    ObjectViewField(name="status", type="string", term_set="status.code", source_column="status_code"),
                ],
            ),
        ],
    )
    sql = "SELECT * FROM sales_bo WHERE status_code = '待办'"
    result = resolve_sql_literals(sql, payload, "ds1", loader)
    assert "status_code = 'TODO'" in result
    assert "'待办'" not in result


def test_resolve_sql_literals_no_term_set_passthrough() -> None:
    """无 term_set 的字段不替换。"""
    loader = TermLoader.from_mapping({"status.code": [{"code": "TODO", "label": "待办"}]})
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="s1", source_type="DB", datasource_alias="ds1")],
        objects=[
            ObjectViewObject(
                object_id="o1",
                object_name="Sales",
                source_id="s1",
                table="sales_bo",
                fields=[
                    ObjectViewField(name="name", type="string", term_set=None, source_column="name"),
                ],
            ),
        ],
    )
    sql = "SELECT * FROM sales_bo WHERE name = '测试'"
    result = resolve_sql_literals(sql, payload, "ds1", loader)
    assert "name = '测试'" in result


def test_resolve_sql_literals_no_payload_passthrough() -> None:
    """无 payload 时原样返回。"""
    loader = TermLoader.from_mapping({"status.code": [{"code": "TODO", "label": "待办"}]})
    sql = "SELECT * FROM sales_bo WHERE status_code = '待办'"
    result = resolve_sql_literals(sql, None, "ds1", loader)
    assert result == sql


def test_resolve_sql_literals_with_table_alias() -> None:
    """FROM sales_bo sb WHERE sb.status_code = '待办' 替换为 'TODO'。"""
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="s1", source_type="DB", datasource_alias="ds1")],
        objects=[
            ObjectViewObject(
                object_id="o1",
                object_name="Sales",
                source_id="s1",
                table="sales_bo",
                fields=[
                    ObjectViewField(name="status", type="string", term_set="status.code", source_column="status_code"),
                ],
            ),
        ],
    )
    sql = "SELECT * FROM sales_bo sb WHERE sb.status_code = '待办'"
    result = resolve_sql_literals(sql, payload, "ds1", loader)
    assert "sb.status_code = 'TODO'" in result
    assert "'待办'" not in result


def test_resolve_sql_literals_no_loader_passthrough() -> None:
    """无 term_loader 时原样返回。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="s1", source_type="DB", datasource_alias="ds1")],
        objects=[
            ObjectViewObject(
                object_id="o1",
                object_name="Sales",
                source_id="s1",
                table="sales_bo",
                fields=[
                    ObjectViewField(name="status", type="string", term_set="status.code", source_column="status_code"),
                ],
            ),
        ],
    )
    sql = "SELECT * FROM sales_bo WHERE status_code = '待办'"
    result = resolve_sql_literals(sql, payload, "ds1", None)
    assert result == sql
