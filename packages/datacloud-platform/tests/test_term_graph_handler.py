"""术语知识图谱查询 Handler 单元测试。

测试 _term_get_knowledge_by_word 和 _fetch_relations_recursive 函数。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from datacloud_platform.api.routers.rpc.handlers.term import (
    _fetch_relations_recursive,
    _term_get_knowledge_by_word,
)


class FakeRequest:
    """测试用伪 Request 对象。"""


def test_missing_keywords_raises_error() -> None:
    """测试缺少 keywords 参数时抛出异常。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"searchLevel": "1"}

    with pytest.raises(ValueError, match="keywords is required"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_keywords_not_list_raises_error() -> None:
    """测试 keywords 不是列表时抛出异常。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"keywords": "byDC"}

    with pytest.raises(ValueError, match="keywords must be a list"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_keywords_exceed_limit_raises_error() -> None:
    """测试 keywords 超过 20 个时抛出异常。"""
    mock_platform = Mock()
    params: dict[str, Any] = {"keywords": [f"term{i}" for i in range(25)]}

    with pytest.raises(ValueError, match="keywords list exceeds maximum limit of 20"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]


def test_term_not_found_returns_error() -> None:
    """测试术语不存在时返回错误信息。"""
    mock_platform = Mock()
    mock_platform.search_terms.return_value = {"data": []}

    params: dict[str, Any] = {
        "keywords": ["不存在的术语"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result["resultCode"] == "0"
    assert "error" in result["resultObject"]


def test_single_keyword_basic_query() -> None:
    """测试单个关键词基础查询。"""
    mock_platform = Mock()
    mock_platform.search_terms.return_value = {
        "data": [
            {
                "id": "term-001",
                "term_name": "byDC",
                "term_code": "byDC",
                "term_type": "Product",
            }
        ]
    }
    mock_platform.query_term_relations.return_value = {"data": []}

    params: dict[str, Any] = {
        "keywords": ["byDC"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result["resultCode"] == "0"
    assert "root_terms" in result["resultObject"]
    assert len(result["resultObject"]["root_terms"]) == 1
    assert result["resultObject"]["root_terms"][0]["term_name"] == "byDC"


def test_batch_keywords_query_with_deduplication() -> None:
    """测试批量关键词查询，验证去重逻辑。"""
    mock_platform = Mock()

    # 模拟两个关键词查到相同术语
    mock_platform.search_terms.side_effect = [
        {"data": [{"id": "term-001", "term_name": "byDC"}]},
        {"data": [{"id": "term-001", "term_name": "byDC"}]},
    ]
    mock_platform.query_term_relations.return_value = {"data": []}

    params: dict[str, Any] = {
        "keywords": ["byDC", "百应数据云"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result["resultCode"] == "0"
    # 验证去重：两个关键词查到同一术语，只返回一个
    assert len(result["resultObject"]["root_terms"]) == 1


def test_fetch_relations_recursive_respects_max_level() -> None:
    """测试递归获取关系时遵守最大深度限制。"""
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [
            {
                "relation_id": "rel-001",
                "target_term_id": "term-002",
                "relation_category": "part-of",
                "direction": "outbound",
                "target_term": {"id": "term-002", "term_name": "本体库"},
            }
        ]
    }

    visited: set[str] = set()
    result = _fetch_relations_recursive(
        mock_platform, "base_id", "term-001", 1, 1, visited
    )

    # 只查询 1 跳，不递归到第 2 跳
    assert len(result) == 1
    assert result[0]["level"] == 1
    assert mock_platform.query_term_relations.call_count == 1


def test_fetch_relations_recursive_avoids_cycles() -> None:
    """测试递归获取关系时避免循环引用。"""
    mock_platform = Mock()
    mock_platform.query_term_relations.return_value = {
        "data": [
            {
                "relation_id": "rel-001",
                "target_term_id": "term-001",
                "relation_category": "relates-to",
                "direction": "outbound",
                "target_term": {"id": "term-001", "term_name": "循环引用"},
            }
        ]
    }

    visited: set[str] = {"term-001"}
    result = _fetch_relations_recursive(
        mock_platform, "base_id", "term-001", 1, 5, visited
    )

    # 已访问过的术语不会重复遍历
    assert len(result) == 0


def test_return_knowledge_fetches_term_knowledge() -> None:
    """测试 returnTermOrKnowledge=knowledge 时获取知识明细。"""
    mock_platform = Mock()
    mock_platform.search_terms.return_value = {
        "data": [{"id": "term-001", "term_name": "本体库"}]
    }
    mock_platform.query_term_relations.return_value = {
        "data": [
            {
                "relation_id": "rel-001",
                "target_term_id": "term-002",
                "direction": "outbound",
                "target_term": {"id": "term-002", "term_name": "对象"},
            }
        ]
    }
    mock_platform.list_term_knowledges.return_value = {
        "data": [
            {
                "knowledge_id": "kb-001",
                "ext_kb_id": "78",
                "ext_file_path": "/Concept/对象.md",
            }
        ]
    }

    params: dict[str, Any] = {
        "keywords": ["本体库"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "knowledge",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result["resultCode"] == "0"
    assert len(result["resultObject"]["graph"]) == 1
    assert "knowledge" in result["resultObject"]["graph"][0]
    mock_platform.list_term_knowledges.assert_called_once()


def test_search_level_all_sets_high_max_level() -> None:
    """测试 searchLevel=all 时设置高递归深度。"""
    mock_platform = Mock()
    mock_platform.search_terms.return_value = {
        "data": [{"id": "term-001", "term_name": "byDC"}]
    }
    mock_platform.query_term_relations.return_value = {"data": []}

    params: dict[str, Any] = {
        "keywords": ["byDC"],
        "searchLevel": "all",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())  # type: ignore[arg-type]

    assert result["resultCode"] == "0"
    # searchLevel=all 内部转换为 999
