"""术语知识图谱查询 Handler 单元测试 — queryProfile 验证与简化委托。

测试范围：
1. 参数校验：keywords/term_ids 缺失、类型、超限、queryProfile 无效、max_candidates 越界
2. Profile 解析与默认值：graph_fast / graph_deep 默认参数验证
3. 显式覆盖：searchLevel / max_candidates 覆盖 profile 默认值
4. Debug 守卫：非 debug profile 阻断高级参数
5. 委托验证：简化 handler 委托到 platform.query_knowledge_graph()
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from datacloud_platform.api.routers.rpc.handlers.term import (
    _term_get_knowledge_by_word,
)
from datacloud_platform.models.graph_query import (
    GRAPH_QUERY_PROFILE_DEFAULTS,
    _parse_query_profile,
    _parse_search_level,
    _resolve_graph_query_options,
)


class FakeRequest:
    """测试用伪 Request 对象。"""


# ============================================================================
# 参数校验测试
# ============================================================================


def test_missing_keywords_and_term_ids_raises_error() -> None:
    """keywords 和 term_ids 都未提供时抛出 ValueError。"""
    mock_platform = Mock()
    params: dict[str, Any] = {}

    with pytest.raises(ValueError, match="keywords or term_ids"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_keywords_not_list_raises_error() -> None:
    """keywords 不是列表时抛出 ValueError。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"keywords": "not_a_list"}

    with pytest.raises(ValueError, match="keywords must be a list"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_keywords_exceed_limit_raises_error() -> None:
    """keywords 超过 20 个时抛出 ValueError。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"keywords": [f"term{i}" for i in range(25)]}

    with pytest.raises(ValueError, match="keywords list exceeds maximum limit"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_term_ids_not_list_raises_error() -> None:
    """term_ids 不是列表时抛出 ValueError。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"term_ids": "not_a_list"}

    with pytest.raises(ValueError, match="term_ids must be a list"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_term_ids_exceed_limit_raises_error() -> None:
    """term_ids 超过 20 个时抛出 ValueError。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"term_ids": [f"id-{i}" for i in range(25)]}

    with pytest.raises(ValueError, match="term_ids list exceeds maximum limit"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_invalid_query_profile_raises_error() -> None:
    """无效的 queryProfile 抛出 ValueError。"""
    with pytest.raises(ValueError, match="queryProfile must be one of"):
        _parse_query_profile({"queryProfile": "invalid_profile"})


def test_max_candidates_out_of_range_raises_error() -> None:
    """max_candidates 超出 1-20 范围时抛出 ValueError。"""
    with pytest.raises(ValueError, match="max_candidates must be between"):
        _resolve_graph_query_options({"max_candidates": "50"}, "graph_fast")

    with pytest.raises(ValueError, match="max_candidates must be between"):
        _resolve_graph_query_options({"max_candidates": "0"}, "graph_fast")


# ============================================================================
# Profile 解析与默认值测试
# ============================================================================


def test_graph_fast_profile_applied() -> None:
    """graph_fast profile 应用正确的默认值。"""
    options = _resolve_graph_query_options({"queryProfile": "graph_fast"}, "graph_fast")
    defaults = GRAPH_QUERY_PROFILE_DEFAULTS["graph_fast"]

    assert options.query_profile == "graph_fast"
    assert options.max_level == defaults.max_level  # 1
    assert options.top_k == defaults.top_k  # 20
    assert options.max_candidates == defaults.max_candidates  # 5
    assert options.max_edges_per_root == defaults.max_edges_per_root  # 100
    assert options.direction == defaults.direction  # "both"


def test_graph_deep_profile_applied() -> None:
    """graph_deep profile 应用正确的默认值。"""
    options = _resolve_graph_query_options({"queryProfile": "graph_deep"}, "graph_deep")
    defaults = GRAPH_QUERY_PROFILE_DEFAULTS["graph_deep"]

    assert options.query_profile == "graph_deep"
    assert options.max_level == defaults.max_level  # 2
    assert options.top_k == defaults.top_k  # 50
    assert options.max_candidates == defaults.max_candidates  # 10
    assert options.max_edges_per_root == defaults.max_edges_per_root  # 300
    assert options.direction == defaults.direction  # "both"


def test_graph_deep_default_top_k() -> None:
    """graph_deep 的 top_k 默认为 50。"""
    defaults = GRAPH_QUERY_PROFILE_DEFAULTS["graph_deep"]
    assert defaults.top_k == 50


def test_explicit_search_level_overrides_profile() -> None:
    """searchLevel 显式值覆盖 profile 默认深度。"""
    options = _resolve_graph_query_options(
        {"queryProfile": "graph_fast", "searchLevel": "3"},
        "graph_fast",
    )
    assert options.max_level == 3  # 覆盖 graph_fast 默认的 1


def test_explicit_max_candidates_overrides_profile() -> None:
    """max_candidates 显式值覆盖 profile 默认候选数。"""
    options = _resolve_graph_query_options(
        {"queryProfile": "graph_deep", "max_candidates": "3"},
        "graph_deep",
    )
    assert options.max_candidates == 3  # 覆盖 graph_deep 默认的 10


def test_search_level_all_sets_max() -> None:
    """searchLevel=all 转换为 999。"""
    level = _parse_search_level("all", 1)
    assert level == 999


def test_search_level_zero_sets_zero() -> None:
    """searchLevel=0 转换为 0（仅返回术语本身）。"""
    level = _parse_search_level("0", 1)
    assert level == 0


def test_search_level_negative_raises_error() -> None:
    """searchLevel 为负数时抛出 ValueError。"""
    with pytest.raises(ValueError, match="not be negative"):
        _parse_search_level("-1", 1)


# ============================================================================
# Debug 守卫测试
# ============================================================================


def test_non_debug_blocks_advanced_params() -> None:
    """graph_fast / graph_deep profile 阻断 direction 等高级参数。"""
    blocked_fields = [
        "direction",
        "relationPageLimit",
        "relationTotalLimit",
        "relationTypes",
        "objectTypes",
    ]

    for field in blocked_fields:
        with pytest.raises(ValueError, match=f"{field} is only allowed"):
            _resolve_graph_query_options(
                {"queryProfile": "graph_fast", field: "value"},
                "graph_fast",
            )


def test_graph_debug_allows_advanced_params() -> None:
    """graph_debug profile 允许 direction 等高级参数。"""
    options = _resolve_graph_query_options(
        {
            "queryProfile": "graph_debug",
            "direction": "outbound",
            "maxEdgesPerRoot": "200",
        },
        "graph_debug",
    )
    assert options.direction == "outbound"
    assert options.max_edges_per_root == 200


# ============================================================================
# 委托测试：简化 handler → platform.query_knowledge_graph()
# ============================================================================


def _build_stub_result(
    root_terms: list[dict[str, Any]], total_terms: int
) -> dict[str, Any]:
    """构造 query_knowledge_graph 返回的 data 结构。"""
    return {"root_terms": root_terms, "total_terms": total_terms}


def test_simplified_handler_calls_query_knowledge_graph() -> None:
    """简化 handler 正确委托到 platform.query_knowledge_graph。"""
    mock_platform = Mock()
    mock_platform.query_knowledge_graph.return_value = _build_stub_result(
        [{"term_id": "term-001", "term_name": "byDC", "graph": [], "max_depth": 0}],
        total_terms=1,
    )

    params: dict[str, Any] = {"keywords": ["byDC"], "queryProfile": "graph_fast"}
    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result.code == 200
    assert result.data["root_terms"][0]["term_name"] == "byDC"
    mock_platform.query_knowledge_graph.assert_called_once()


def test_handler_passes_query_profile_to_platform() -> None:
    """Handler 将 queryProfile 解析为 GraphQueryOptions 传递给平台。"""
    mock_platform = Mock()
    mock_platform.query_knowledge_graph.return_value = _build_stub_result(
        [{"term_id": "t1", "term_name": "X", "graph": [], "max_depth": 0}], 1
    )

    params: dict[str, Any] = {"keywords": ["X"], "queryProfile": "graph_deep"}
    _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    call_kwargs = mock_platform.query_knowledge_graph.call_args.kwargs
    options = call_kwargs["options"]
    assert options.query_profile == "graph_deep"


def test_handler_passes_term_ids_to_platform() -> None:
    """Handler 将 term_ids 参数传递给平台调用。"""
    mock_platform = Mock()
    mock_platform.query_knowledge_graph.return_value = _build_stub_result(
        [{"term_id": "term-a", "term_name": "A", "graph": [], "max_depth": 0}], 1
    )

    params: dict[str, Any] = {"term_ids": ["term-a", "term-b"]}
    _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    call_kwargs = mock_platform.query_knowledge_graph.call_args.kwargs
    assert call_kwargs["term_ids"] == ["term-a", "term-b"]


def test_handler_converts_kb_ids_to_set() -> None:
    """Handler 将 kb_ids 列表转换为 set 后传递给平台。"""
    mock_platform = Mock()
    mock_platform.query_knowledge_graph.return_value = _build_stub_result([], 0)

    params: dict[str, Any] = {"keywords": ["测试"], "kb_ids": ["78", "99"]}
    _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    call_kwargs = mock_platform.query_knowledge_graph.call_args.kwargs
    assert call_kwargs["kb_ids"] == {"78", "99"}
