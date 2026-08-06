"""_term_get_relations Handler 单元测试 — term_type_code 透传与向后兼容。

测试范围：
1. 传 term_type_code → kwargs 透传到 platform.query_term_relations
2. 不传 term_type_code → kwargs 不含该键（行为与改造前一致）
3. 传空字符串 term_type_code → 视为无值，不传（有值才传语义）

注：SQL JOIN 过滤与 updated_time DESC 排序在 opengauss reader 层实现，
无 DB 集成测试基建，此处仅覆盖 handler 参数契约。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

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


def test_passes_term_type_code_to_platform() -> None:
    """传 term_type_code 时透传到 platform.query_term_relations。"""
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [],
        "pageIndex": 1,
        "pageSize": 20,
        "totalCount": 0,
        "totalPages": 0,
    }

    result = _term_get_relations(
        mock_platform,
        _build_params(term_type_code="Concept"),
        FakeRequest(),  # type: ignore[arg-type]
    )

    assert result.code == 200
    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert call_kwargs["term_type_code"] == "Concept"
    assert call_kwargs["term_id"] == "term-001"
    assert call_kwargs["direction"] == "both"


def test_omits_term_type_code_when_absent() -> None:
    """不传 term_type_code 时 kwargs 不含该键（向后兼容）。"""
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [],
        "pageIndex": 1,
        "pageSize": 20,
        "totalCount": 0,
        "totalPages": 0,
    }

    _term_get_relations(
        mock_platform,
        _build_params(),
        FakeRequest(),  # type: ignore[arg-type]
    )

    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert "term_type_code" not in call_kwargs


def test_omits_term_type_code_when_empty_string() -> None:
    """传空字符串 term_type_code 视为无值，不传入 kwargs。"""
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [],
        "pageIndex": 1,
        "pageSize": 20,
        "totalCount": 0,
        "totalPages": 0,
    }

    _term_get_relations(
        mock_platform,
        _build_params(term_type_code=""),
        FakeRequest(),  # type: ignore[arg-type]
    )

    call_kwargs = mock_platform.query_term_relations.call_args.kwargs
    assert "term_type_code" not in call_kwargs
