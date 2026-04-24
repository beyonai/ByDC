"""VirtualActionValidator.validate_analyze 维度 group_op 与字段类型校验测试。

Bug1：group_op 缺失时 dim.get("group_op", "") 返回 ""，
      "" 不在 allowed_gops 中导致误报 VIRTUAL_ACTION_ERR_UNSUPPORTED_OP。
修复方向：group_op 键不在 dim 中时跳过校验（未传时不约束）。

Bug2：指标类字段（analytic_kind 为 metric 系列）可被放入 dimensions，
      导致 GROUP BY 指标列，语义错误。
修复方向：validate_analyze 中检测 dimensions 字段的 analytic_kind，
          属于 _METRIC_KINDS 时报 VIRTUAL_ACTION_ERR_UNSUPPORTED_OP。
"""

from __future__ import annotations

import pytest
from datacloud_data_sdk.virtual_action.validator import (
    VirtualActionValidationError,
    VirtualActionValidator,
)

# ---------------------------------------------------------------------------
# 极简 stub field —— 只需满足 _field_map / _get_field 所需接口
# ---------------------------------------------------------------------------


class _Field:
    def __init__(
        self,
        field_code: str,
        group_ops: list[str] | None = None,
        analytic_kind: str | None = None,
    ) -> None:
        self.field_code = field_code
        self.field_name = field_code
        self.group_ops = group_ops or []
        self.analytic_kind = analytic_kind


def _make_validator(group_ops: list[str] | None = None) -> VirtualActionValidator:
    """返回含单个字段 'revenue' 的校验器，group_ops 可自定义。"""
    field = _Field("revenue", group_ops=group_ops)
    return VirtualActionValidator([field])


# ---------------------------------------------------------------------------
# TC-A：group_op 键缺失 → 不应触发 UNSUPPORTED_OP 异常
# ---------------------------------------------------------------------------


def test_group_op_absent_should_not_raise() -> None:
    """维度中没有 group_op 键时，不应因 '' not in allowed_gops 而报错。"""
    validator = _make_validator(group_ops=["self", "range"])
    # dimension 不含 group_op 键
    args = {
        "dimensions": [{"field": "revenue"}],
        "metrics": [{"field": "revenue", "agg": "sum"}],
    }
    # 不应抛出异常
    validator.validate_analyze(args)


# ---------------------------------------------------------------------------
# TC-B：group_op 明确设为非法值 → 仍然报错
# ---------------------------------------------------------------------------


def test_group_op_invalid_value_should_raise() -> None:
    """group_op 明确传入不在 allowed_gops 的值时，必须报 UNSUPPORTED_OP。"""
    validator = _make_validator(group_ops=["self", "range"])
    args = {
        "dimensions": [{"field": "revenue", "group_op": "year"}],
        "metrics": [{"field": "revenue", "agg": "sum"}],
    }
    with pytest.raises(VirtualActionValidationError) as exc_info:
        validator.validate_analyze(args)
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"


# ---------------------------------------------------------------------------
# TC-C：group_op="range" 键缺失 → 不应触发 range/buckets 检查
# ---------------------------------------------------------------------------


def test_group_op_range_absent_does_not_check_buckets() -> None:
    """group_op 键不存在时，不应触发 'range 必须携带 buckets' 校验。"""
    validator = _make_validator(group_ops=["self", "range"])
    args = {
        "dimensions": [{"field": "revenue"}],  # 无 group_op，无 buckets
        "metrics": [{"field": "revenue", "agg": "sum"}],
    }
    # 不应抛出异常
    validator.validate_analyze(args)


# ---------------------------------------------------------------------------
# TC-D：group_op="range" 明确存在但无 buckets → 仍然报错
# ---------------------------------------------------------------------------


def test_group_op_range_present_without_buckets_should_raise() -> None:
    """group_op='range' 明确存在但 buckets 缺失时，必须报错。"""
    validator = _make_validator(group_ops=["self", "range"])
    args = {
        "dimensions": [{"field": "revenue", "group_op": "range"}],
        "metrics": [{"field": "revenue", "agg": "sum"}],
    }
    with pytest.raises(VirtualActionValidationError) as exc_info:
        validator.validate_analyze(args)
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"


# ---------------------------------------------------------------------------
# TC-E：指标类 analytic_kind 字段放入 dimensions → 必须报 UNSUPPORTED_OP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric_kind",
    ["basic_metric", "snapshot_metric", "derived_metric", "formula_metric"],
)
def test_metric_field_in_dimensions_should_raise(metric_kind: str) -> None:
    """指标类字段以 self/month 等方式放入 dimensions 时必须报 UNSUPPORTED_OP。

    group_op 缺失等同于 self，同样被拦截。
    """
    metric_field = _Field("revenue", analytic_kind=metric_kind)
    dim_field = _Field("region")
    validator = VirtualActionValidator([metric_field, dim_field])
    args = {
        "dimensions": [{"field": "revenue"}],  # 无 group_op → 等同于 self → 应报错
        "metrics": [{"field": "region", "agg": "count_all"}],
    }
    with pytest.raises(VirtualActionValidationError) as exc_info:
        validator.validate_analyze(args)
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"
    assert "revenue" in str(exc_info.value)
    assert metric_kind in str(exc_info.value)


# ---------------------------------------------------------------------------
# TC-F：非指标类字段放入 dimensions → 允许通过
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "analytic_kind",
    [None, "id", "name", "period", "datetime", "numeric", "virtual_tag"],
)
def test_non_metric_field_in_dimensions_should_pass(analytic_kind: str | None) -> None:
    """非指标类字段（维度、标签、账期等）作为分组维度时不应报错。"""
    dim_field = _Field("region", analytic_kind=analytic_kind)
    metric_field = _Field("revenue", analytic_kind="basic_metric")
    validator = VirtualActionValidator([dim_field, metric_field])
    args = {
        "dimensions": [{"field": "region"}],
        "metrics": [{"field": "revenue", "agg": "sum"}],
    }
    # 不应抛出异常
    validator.validate_analyze(args)


# ---------------------------------------------------------------------------
# TC-G：指标类字段以 group_op=range 放入 dimensions → 允许通过
# （range 区间分桶将指标转为分类维度，是合法的分析模式）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric_kind",
    ["basic_metric", "snapshot_metric", "derived_metric", "formula_metric"],
)
def test_metric_field_with_range_in_dimensions_should_pass(metric_kind: str) -> None:
    """指标类字段以 group_op=range（区间分桶）作为维度时应允许通过。"""
    metric_field = _Field("revenue", analytic_kind=metric_kind, group_ops=["range"])
    dim_field = _Field("region")
    validator = VirtualActionValidator([metric_field, dim_field])
    args = {
        "dimensions": [
            {
                "field": "revenue",
                "group_op": "range",
                "buckets": [{"from": None, "to": 1_000_000, "label": "100万以下"}],
            }
        ],
        "metrics": [{"field": "region", "agg": "count_all"}],
    }
    # 不应抛出异常
    validator.validate_analyze(args)
