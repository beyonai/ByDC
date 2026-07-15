"""术语知识图谱查询功能测试。

测试范围：
1. 单术语查询 - 基础1跳
2. 单术语查询 - 多跳（2跳）
3. 单术语查询 - 包含知识明细
4. 单术语查询 - 双向关系
5. 单术语查询 - 全部跳数
6. 批量术语查询 - 基础
7. 异常情况 - 术语不存在
8. 异常情况 - 参数校验
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from datacloud_platform.api.routers.rpc.handlers.term import (
    _term_get_knowledge_by_word,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


class FakeRequest:
    """用于测试的伪 Request 对象。"""


@pytest.fixture
def mock_platform(mocker: Any) -> Any:
    """创建 Mock Platform 对象。"""
    platform = mocker.Mock(spec=DatacloudPlatform)
    return platform


def test_single_term_basic_1_hop(mock_platform: Any) -> None:
    """测试用例 8.1: 单术语查询 - 基础1跳。"""
    # 模拟 search_terms 返回结果
    mock_platform.search_terms.return_value = {
        "data": [
            {
                "id": "term-001",
                "term_name": "byDC",
                "term_code": "byDC",
                "term_type": "Product",
                "definition": "百应数据云产品",
            }
        ]
    }

    # 模拟 query_term_relations 返回结果（1跳关系）
    mock_platform.query_term_relations.return_value = {
        "data": [
            {
                "relation_id": "rel-001",
                "source_term_id": "term-001",
                "target_term_id": "term-002",
                "relation_category": "part-of",
                "direction": "outbound",
                "target_term": {
                    "id": "term-002",
                    "term_name": "本体库",
                    "term_code": "ontology_repo",
                    "term_type": "Concept",
                    "definition": "本体的组织单元",
                },
            }
        ],
        "total": 1,
    }

    params = {
        "keywords": ["byDC"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())

    # 验证返回结果结构
    assert result["resultCode"] == "0"
    assert "resultObject" in result
    assert "root_terms" in result["resultObject"]
    assert len(result["resultObject"]["root_terms"]) == 1
    assert result["resultObject"]["root_terms"][0]["term_name"] == "byDC"
    assert "graph" in result["resultObject"]
    assert result["resultObject"]["total_terms"] >= 1


def test_single_term_2_hops(mock_platform: Any) -> None:
    """测试用例 8.2: 单术语查询 - 多跳（2跳）。"""
    mock_platform.search_terms.return_value = {
        "data": [
            {
                "id": "term-001",
                "term_name": "对象",
                "term_code": "object",
                "term_type": "Concept",
                "definition": "现实世界实体或事件的模式定义",
            }
        ]
    }

    # 模拟第1跳关系
    mock_platform.query_term_relations.side_effect = [
        {
            "data": [
                {
                    "relation_id": "rel-001",
                    "source_term_id": "term-001",
                    "target_term_id": "term-002",
                    "relation_category": "part-of",
                    "direction": "outbound",
                    "target_term": {
                        "id": "term-002",
                        "term_name": "属性",
                        "term_code": "property",
                        "term_type": "Concept",
                    },
                }
            ],
            "total": 1,
        },
        # 模拟第2跳关系
        {
            "data": [
                {
                    "relation_id": "rel-002",
                    "source_term_id": "term-002",
                    "target_term_id": "term-003",
                    "relation_category": "maps-to",
                    "direction": "outbound",
                    "target_term": {
                        "id": "term-003",
                        "term_name": "字段",
                        "term_code": "field",
                        "term_type": "Technical",
                    },
                }
            ],
            "total": 1,
        },
    ]

    params = {
        "keywords": ["对象"],
        "searchLevel": "2",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())

    assert result["resultCode"] == "0"
    assert result["resultObject"]["max_level_reached"] == 2
    assert result["resultObject"]["total_terms"] >= 2


def test_single_term_with_knowledge(mock_platform: Any) -> None:
    """测试用例 8.3: 单术语查询 - 包含知识明细。"""
    mock_platform.search_terms.return_value = {
        "data": [
            {
                "id": "term-001",
                "term_name": "本体库",
                "term_code": "ontology_repo",
                "term_type": "Concept",
            }
        ]
    }

    mock_platform.query_term_relations.return_value = {
        "data": [
            {
                "relation_id": "rel-001",
                "source_term_id": "term-001",
                "target_term_id": "term-002",
                "relation_category": "part-of",
                "direction": "outbound",
                "target_term": {
                    "id": "term-002",
                    "term_name": "对象",
                    "term_code": "object",
                    "term_type": "Concept",
                },
            }
        ],
        "total": 1,
    }

    # 模拟知识库查询
    mock_platform.list_term_knowledges.return_value = {
        "data": [
            {
                "knowledge_id": "kb-001",
                "term_id": "term-001",
                "ext_system": "byKnowledge",
                "ext_kb_id": "78",
                "ext_file_path": "/Concept/本体库.md",
            }
        ]
    }

    params = {
        "keywords": ["本体库"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "knowledge",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())

    assert result["resultCode"] == "0"
    graph = result["resultObject"]["graph"]
    assert len(graph) > 0
    # 验证知识明细字段存在
    for node in graph:
        assert "knowledge" in node


def test_term_not_found(mock_platform: Any) -> None:
    """测试用例 8.11: 异常情况 - 术语不存在。"""
    mock_platform.search_terms.return_value = {"data": []}

    params = {
        "keywords": ["不存在的术语XYZ123"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())

    assert result["resultCode"] == "0"
    assert "error" in result["resultObject"]


def test_missing_required_params() -> None:
    """测试用例 8.12: 异常情况 - 参数校验（缺少必填参数）。"""
    mock_platform = None

    params = {"searchLevel": "1"}

    with pytest.raises(ValueError, match="keywords is required"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())


def test_batch_keywords_query(mock_platform: Any) -> None:
    """测试用例 8.7: 批量术语查询 - 基础。"""
    # 模拟多个关键词的搜索结果
    mock_platform.search_terms.side_effect = [
        {
            "data": [
                {
                    "id": "term-001",
                    "term_name": "byDC",
                    "term_code": "byDC",
                    "term_type": "Product",
                }
            ]
        },
        {
            "data": [
                {
                    "id": "term-002",
                    "term_name": "本体库",
                    "term_code": "ontology_repo",
                    "term_type": "Concept",
                }
            ]
        },
        {
            "data": [
                {
                    "id": "term-003",
                    "term_name": "对象",
                    "term_code": "object",
                    "term_type": "Concept",
                }
            ]
        },
    ]

    mock_platform.query_term_relations.return_value = {"data": [], "total": 0}

    params = {
        "keywords": ["byDC", "本体库", "对象"],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    result = _term_get_knowledge_by_word(mock_platform, params, FakeRequest())

    assert result["resultCode"] == "0"
    assert len(result["resultObject"]["root_terms"]) == 3


def test_keywords_exceed_limit() -> None:
    """测试用例 8.10: 批量术语查询 - 超出限制。"""
    mock_platform = None

    params = {
        "keywords": [f"term{i}" for i in range(25)],
        "searchLevel": "1",
        "returnTermOrKnowledge": "term",
    }

    with pytest.raises(ValueError, match="keywords list exceeds maximum limit of 20"):
        _term_get_knowledge_by_word(mock_platform, params, FakeRequest())
