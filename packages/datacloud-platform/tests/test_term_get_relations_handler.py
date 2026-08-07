"""_term_get_relations Handler 单元测试 — term_type_codes 列表透传与参数校验。

测试范围：
1. 传 term_type_codes 列表 → 清洗后透传到 platform.query_term_relations
2. 不传 term_type_codes → kwargs 不含该键（行为与改造前一致）
3. 空列表 → 视为无过滤，不传（向后兼容）
4. 非 list → 抛 ValueError（参照 keywords 校验风格，由框架转 400）
5. 元素清洗：去空白、丢空串；全空串等价于不传

注：SQL IN 过滤与 updated_time DESC 排序在 opengauss reader 层实现，
无 DB 集成测试基建，此处仅覆盖 handler 参数契约。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from datacloud_platform.api.routers.rpc.handlers.term import _term_get_relations


class FakeRequest:
    """测试用伪 Request 对象。"""


def _build_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "base_id": "base-a",
        "id": "term-001",
        "direction": "both",
    }
    params.update(overrides)
    return params


def _mock_platform() -> Mock:
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [],
        "pageIndex": 1,
        "pageSize": 20,
        "totalCount": 0,
        "totalPages": 0,
    }
    return mock_platform


def test_passes_term_type_codes_to_platform() -> None:
    """传 term_type_codes 列表时透传到 platform.query_term_relations。"""
    mock_platform = _mock_platform()

    result = _term_get_relations(
        mock_platform,
        _build_params(term_type_codes=["Concept", "Object"]),
        FakeRequest(),  # type: ignore[arg-type]
    )

    assert result.code == 200
    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert call_kwargs["term_type_codes"] == ["Concept", "Object"]
    assert call_kwargs["term_id"] == "term-001"
    assert call_kwargs["direction"] == "both"


def test_omits_term_type_codes_when_absent() -> None:
    """不传 term_type_codes 时 kwargs 不含该键（向后兼容）。"""
    mock_platform = _mock_platform()

    _term_get_relations(
        mock_platform,
        _build_params(),
        FakeRequest(),  # type: ignore[arg-type]
    )

    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert "term_type_codes" not in call_kwargs


def test_omits_term_type_codes_when_empty_list() -> None:
    """传空列表视为无过滤，不传（向后兼容）。"""
    mock_platform = _mock_platform()

    _term_get_relations(
        mock_platform,
        _build_params(term_type_codes=[]),
        FakeRequest(),  # type: ignore[arg-type]
    )

    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert "term_type_codes" not in call_kwargs


def test_raises_when_term_type_codes_not_list() -> None:
    """非 list（如字符串）→ ValueError（由框架转 400）。"""
    mock_platform = _mock_platform()

    with pytest.raises(ValueError, match="term_type_codes must be a list"):
        _term_get_relations(
            mock_platform,
            _build_params(term_type_codes="Concept"),
            FakeRequest(),  # type: ignore[arg-type]
        )


def test_strips_and_drops_blank_elements() -> None:
    """元素清洗：去空白、丢空串；全空串等价于不传。"""
    mock_platform = _mock_platform()

    _term_get_relations(
        mock_platform,
        _build_params(term_type_codes=[" Concept ", "", "  ", "Object"]),
        FakeRequest(),  # type: ignore[arg-type]
    )

    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert call_kwargs["term_type_codes"] == ["Concept", "Object"]

    # 全空串 → 视为无过滤，不传
    mock_platform = _mock_platform()
    _term_get_relations(
        mock_platform,
        _build_params(term_type_codes=["", "  "]),
        FakeRequest(),  # type: ignore[arg-type]
    )
    assert "term_type_codes" not in mock_platform.query_term_relations.call_args.kwargs
