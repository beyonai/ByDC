"""VirtualActionValidator.validate_analyze 维度 group_op 校验测试。

Bug：group_op 缺失时 dim.get("group_op", "") 返回 ""，
     "" 不在 allowed_gops 中导致误报 VIRTUAL_ACTION_ERR_UNSUPPORTED_OP。

修复方向：group_op 键不在 dim 中时跳过校验（未传时不约束）。
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
    ) -> None:
        self.field_code = field_code
        self.field_name = field_code
        self.group_ops = group_ops or []


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
