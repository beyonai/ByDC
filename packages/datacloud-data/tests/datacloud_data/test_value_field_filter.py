"""验收测试：支持字段比较查询（value_field）。

覆盖设计文档中的用例组 A/B/C/D/E：
  A - view_executor_support.build_filters_where
  B - query_executor._build_where
  C - compute_executor._build_filters_where
  D - analyze_executor._build_filters_where
  E - generator._filter_item_schema / _FILTER_CATCHALL_SCHEMA
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from datacloud_data_sdk.executor.analyze_executor import _build_filters_where as analyze_build_where
from datacloud_data_sdk.executor.compute_executor import _build_filters_where as compute_build_where
from datacloud_data_sdk.executor.query_executor import _build_where
from datacloud_data_sdk.executor.view_executor_support import build_filters_where
from datacloud_data_sdk.virtual_action.generator import (
    _FILTER_CATCHALL_SCHEMA,
    _filter_item_schema,
)

# ─────────────────────────────────────────────────────────────────────────────
# 辅助工具
# ─────────────────────────────────────────────────────────────────────────────


def _param_key_builder(prefix: str, fc: str, idx: int) -> str:
    import re

    safe = re.sub(r"[^a-zA-Z0-9]", "_", fc)[:40]
    return f"{prefix}_{safe}_{idx}"


def _make_field(field_code: str, source_column: str | None = None) -> Any:
    return SimpleNamespace(
        field_code=field_code,
        source_column=source_column or field_code,
        analytic_kind=None,
        formula=None,
        field_type="STRING",
        field_name=field_code,
        filter_ops=["eq", "neq", "gt", "gte", "lt", "lte"],
        property_kind="physical",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 用例组 A：view_executor_support.build_filters_where
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildFiltersWhereViewSupport:
    """A 组：视图路径 build_filters_where。"""

    BASE_MAPPING: dict[str, tuple[str, str]] = {
        "actual_online_date": ("t0", "actual_online_date"),
        "plan_online_date": ("t0", "plan_online_date"),
        "project_status": ("t0", "project_status"),
    }

    def test_a1_basic_gt(self) -> None:
        """A-1：基础字段比较 gt，生成正确 SQL，无参数绑定。"""
        sql, params = build_filters_where(
            [{"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"}],
            self.BASE_MAPPING,
            "OPENGAUSS",
            _param_key_builder,
        )
        assert sql == 't0."actual_online_date" > t0."plan_online_date"'
        assert params == {}

    def test_a2_cross_table_lte(self) -> None:
        """A-2：跨表别名 lte。"""
        mapping = {
            "actual_revenue_date": ("t0", "actual_revenue_date"),
            "plan_revenue_date": ("t1", "plan_revenue_date"),
        }
        sql, params = build_filters_where(
            [{"field": "actual_revenue_date", "op": "lte", "value_field": "plan_revenue_date"}],
            mapping,
            "OPENGAUSS",
            _param_key_builder,
        )
        assert sql == 't0."actual_revenue_date" <= t1."plan_revenue_date"'
        assert params == {}

    def test_a3_value_field_takes_priority(self) -> None:
        """A-3：value_field 优先于 value，不产生参数占位符。"""
        sql, params = build_filters_where(
            [
                {
                    "field": "actual_online_date",
                    "op": "gt",
                    "value": "2024-01-01",
                    "value_field": "plan_online_date",
                }
            ],
            self.BASE_MAPPING,
            "OPENGAUSS",
            _param_key_builder,
        )
        assert ":p_" not in sql
        assert params == {}
        assert "actual_online_date" in sql
        assert "plan_online_date" in sql

    def test_a4_unknown_value_field_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """A-4：value_field 不存在时跳过，记录 warning。"""
        with caplog.at_level(logging.WARNING):
            sql, params = build_filters_where(
                [{"field": "actual_online_date", "op": "gt", "value_field": "nonexistent_field"}],
                self.BASE_MAPPING,
                "OPENGAUSS",
                _param_key_builder,
            )
        assert sql == ""
        assert params == {}
        assert "nonexistent_field" in caplog.text

    def test_a5_unsupported_op_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """A-5：value_field 与不支持的 op 组合时跳过，记录 warning。"""
        with caplog.at_level(logging.WARNING):
            sql, params = build_filters_where(
                [{"field": "actual_online_date", "op": "like", "value_field": "plan_online_date"}],
                self.BASE_MAPPING,
                "OPENGAUSS",
                _param_key_builder,
            )
        assert sql == ""
        assert params == {}
        assert "like" in caplog.text

    def test_a6_mixed_filters_and(self) -> None:
        """A-6：value_field + 普通 value，AND 连接。"""
        sql, params = build_filters_where(
            [
                {"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"},
                {"field": "project_status", "op": "eq", "value": "进行中"},
            ],
            self.BASE_MAPPING,
            "OPENGAUSS",
            _param_key_builder,
        )
        parts = sql.split(" AND ")
        assert len(parts) == 2
        assert parts[0] == 't0."actual_online_date" > t0."plan_online_date"'
        assert "project_status" in parts[1]
        assert ":p_" in parts[1]
        assert params.get(list(params.keys())[0]) == "进行中"

    def test_a7_all_supported_ops(self) -> None:
        """A-7：所有支持的 op 均生成正确符号。"""
        op_to_symbol = {
            "eq": "=",
            "neq": "!=",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
        }
        for op, symbol in op_to_symbol.items():
            sql, params = build_filters_where(
                [{"field": "actual_online_date", "op": op, "value_field": "plan_online_date"}],
                self.BASE_MAPPING,
                "OPENGAUSS",
                _param_key_builder,
            )
            assert symbol in sql, f"op={op} 应生成符号 {symbol}，实际 SQL: {sql}"
            assert params == {}


# ─────────────────────────────────────────────────────────────────────────────
# 用例组 B：query_executor._build_where
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildWhereQueryExecutor:
    """B 组：单表路径 _build_where。"""

    FIELD_MAP: dict[str, Any] = {
        "actual_online_date": _make_field("actual_online_date"),
        "plan_online_date": _make_field("plan_online_date"),
        "project_status": _make_field("project_status"),
    }

    def test_b1_basic_gt(self) -> None:
        """B-1：单表字段比较 gt（query WHERE 子句列名不带引号，与原有行为一致）。"""
        sql, params = _build_where(
            [{"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"}],
            self.FIELD_MAP,
            "OPENGAUSS",
        )
        assert sql == "actual_online_date > plan_online_date"
        assert params == {}

    def test_b2_unknown_value_field_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """B-2：value_field 不在 field_map 时跳过，记录 warning。"""
        with caplog.at_level(logging.WARNING):
            sql, params = _build_where(
                [{"field": "actual_online_date", "op": "gt", "value_field": "unknown_field"}],
                self.FIELD_MAP,
                "OPENGAUSS",
            )
        assert sql == ""
        assert params == {}
        assert "unknown_field" in caplog.text

    def test_b3_mixed_filters(self) -> None:
        """B-3：value_field + 普通 value 混合，AND 连接。"""
        sql, params = _build_where(
            [
                {"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"},
                {"field": "project_status", "op": "eq", "value": "进行中"},
            ],
            self.FIELD_MAP,
            "OPENGAUSS",
        )
        parts = sql.split(" AND ")
        assert len(parts) == 2
        assert parts[0] == "actual_online_date > plan_online_date"
        assert "project_status" in parts[1]
        assert len(params) == 1
        assert list(params.values())[0] == "进行中"


# ─────────────────────────────────────────────────────────────────────────────
# 用例组 C：compute_executor._build_filters_where
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildFiltersWhereComputeExecutor:
    """C 组：compute 路径 _build_filters_where。"""

    FIELD_MAP: dict[str, Any] = {
        "actual_online_date": _make_field("actual_online_date"),
        "plan_online_date": _make_field("plan_online_date"),
    }

    def test_c1_basic_gt(self) -> None:
        """C-1：聚合查询中的字段比较 filter（compute WHERE 子句列名不带引号）。"""
        sql, params = compute_build_where(
            [{"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"}],
            self.FIELD_MAP,
            "OPENGAUSS",
        )
        assert sql == "actual_online_date > plan_online_date"
        assert params == {}

    def test_c2_unknown_value_field_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """C-2：value_field 不在 field_map 时跳过，记录 warning。"""
        with caplog.at_level(logging.WARNING):
            sql, params = compute_build_where(
                [{"field": "actual_online_date", "op": "gt", "value_field": "unknown_field"}],
                self.FIELD_MAP,
                "OPENGAUSS",
            )
        assert sql == ""
        assert params == {}
        assert "unknown_field" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例组 D：analyze_executor._build_filters_where
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildFiltersWhereAnalyzeExecutor:
    """D 组：analyze 路径 _build_filters_where。"""

    FIELD_TO_COL: dict[str, str] = {
        "actual_online_date": "actual_online_date",
        "plan_online_date": "plan_online_date",
    }
    FIELD_MAP: dict[str, Any] = {
        "actual_online_date": _make_field("actual_online_date"),
        "plan_online_date": _make_field("plan_online_date"),
    }

    def test_d1_basic_gt(self) -> None:
        """D-1：字段比较 filter。"""
        sql, params = analyze_build_where(
            [{"field": "actual_online_date", "op": "gt", "value_field": "plan_online_date"}],
            self.FIELD_TO_COL,
            self.FIELD_MAP,
            "OPENGAUSS",
        )
        assert sql == '"actual_online_date" > "plan_online_date"'
        assert params == {}

    def test_d2_unknown_value_field_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """D-2：value_field 不在 field_to_col 时跳过，记录 warning。"""
        with caplog.at_level(logging.WARNING):
            sql, params = analyze_build_where(
                [{"field": "actual_online_date", "op": "gt", "value_field": "nonexistent"}],
                self.FIELD_TO_COL,
                self.FIELD_MAP,
                "OPENGAUSS",
            )
        assert sql == ""
        assert params == {}
        assert "nonexistent" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例组 E：generator schema
# ─────────────────────────────────────────────────────────────────────────────


class TestGeneratorSchema:
    """E 组：generator schema 包含 value_field。"""

    def _make_view_field(self) -> Any:
        return SimpleNamespace(
            field_code="plan_online_date",
            field_name="计划上线日期",
            field_type="DATE",
            analytic_kind="datetime",
            analytic_role="dimension",
            filter_ops=["gt", "lt", "gte", "lte"],
            group_ops=["self"],
            aggregate_ops=[],
            term_set=None,
            required_filter_group=None,
        )

    def test_e1_filter_item_schema_has_value_field(self) -> None:
        """E-1：_filter_item_schema 返回的 properties 包含 value_field。"""
        f = self._make_view_field()
        schema = _filter_item_schema(f, strict_field_code=True)
        props = schema["properties"]
        assert "value_field" in props
        assert props["value_field"]["type"] == "string"
        assert "字段引用" in props["value_field"]["description"]

    def test_e2_catchall_schema_has_value_field(self) -> None:
        """E-2：_FILTER_CATCHALL_SCHEMA 包含 value_field。"""
        props = _FILTER_CATCHALL_SCHEMA["properties"]
        assert "value_field" in props
        assert props["value_field"]["type"] == "string"
