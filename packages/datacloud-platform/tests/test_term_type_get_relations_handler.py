"""termType/getRelations handler 参数契约测试（_term_type_get_relations）。

覆盖范围：
1. type_code/direction/relation_category/relation_code/keyword 透传到
   platform.list_term_type_relations
2. 默认值：direction="both"、page_index=1、page_size=20
3. type_code 空字符串也保留在 kwargs 中（reader 层视为"不过滤"，向后兼容）
4. library_id 缺省时回退到 _base(params)

注：SQL JOIN term 过滤在 opengauss reader 层实现（无 DB 集成测试基建），
此处仅覆盖 handler → platform 的参数契约。relation_code 是本次修复补通的
链路缺口（此前 handler 已传但下游无此参数）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from datacloud_platform.api.routers.rpc.handlers.term import _term_type_get_relations


class FakeRequest:
    """测试用伪 Request 对象。"""


EMPTY_PAGE = {
    "data": [],
    "pageIndex": 1,
    "pageSize": 20,
    "totalCount": 0,
    "totalPages": 0,
}


def _build_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"base_id": "base-a", "type_code": "prop"}
    params.update(overrides)
    return params


def _call(params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """调用 handler，返回 (result, 透传给 platform 的 kwargs)。"""
    mock_platform = Mock()
    mock_platform.list_term_type_relations.return_value = EMPTY_PAGE

    result = _term_type_get_relations(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result.code == 200
    return result, mock_platform.list_term_type_relations.call_args.kwargs


def test_passes_all_filters_to_platform() -> None:
    """全部过滤参数原样透传到 platform.list_term_type_relations。"""
    _, kwargs = _call(
        _build_params(
            type_code="prop",
            direction="outgoing",
            relation_category="structural",
            relation_code="has_property",
            keyword="库存",
        )
    )

    assert kwargs["type_code"] == "prop"
    assert kwargs["direction"] == "outgoing"
    assert kwargs["relation_category"] == "structural"
    assert kwargs["relation_code"] == "has_property"
    assert kwargs["keyword"] == "库存"
    assert kwargs["library_id"] == "base-a"


def test_relation_code_flows_through_chain() -> None:
    """relation_code 必须透传（本次修复补通的链路缺口）。"""
    _, kwargs = _call(_build_params(relation_code="is_a"))
    assert kwargs["relation_code"] == "is_a"


def test_defaults_when_optional_params_absent() -> None:
    """未传可选参数时使用默认值 direction=both/page_index=1/page_size=20。"""
    _, kwargs = _call(_build_params())

    assert kwargs["type_code"] == "prop"
    assert kwargs["direction"] == "both"
    assert kwargs["page_index"] == 1
    assert kwargs["page_size"] == 20
    # 未传的可选过滤参数不出现在 kwargs 中
    assert "relation_category" not in kwargs
    assert "relation_code" not in kwargs
    assert "keyword" not in kwargs


def test_empty_type_code_is_kept() -> None:
    """type_code 传空字符串仍保留在 kwargs（reader 层视为不过滤，向后兼容）。"""
    _, kwargs = _call(_build_params(type_code=""))
    assert kwargs["type_code"] == ""


def test_library_id_falls_back_to_base() -> None:
    """未传 library_id/libraryId 时回退到 base_id。"""
    _, kwargs = _call({"base_id": "base-x", "type_code": "prop"})
    assert kwargs["library_id"] == "base-x"


def test_result_is_passthrough_of_platform_return() -> None:
    """handler 返回 platform 的分页结构（data/pageIndex/pageSize/totalCount/totalPages）。"""
    result, _ = _call(_build_params())
    assert result.data == EMPTY_PAGE
