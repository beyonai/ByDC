"""术语知识图谱查询功能测试 — query_knowledge_graph 全流程。

测试范围：
1. 单关键词基础查询
2. 批量关键词去重
3. term_ids 精准查询
4. kb_ids 过滤：搜索过滤 + 关系过滤
5. max_edges 截断
6. 根术语独立 visited 隔离
7. 消歧模式：auto / return_all + max_candidates
8. 无结果错误处理
9. 返回结构验证
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock


from datacloud_knowledge.contracts.term_provider_types import QueryResult
from datacloud_platform.models.graph_query import (
    GRAPH_QUERY_PROFILE_DEFAULTS,
    GraphQueryOptions,
)
from datacloud_platform.mixins.term import TermMixin


class FakeRequest:
    """测试用伪 Request 对象。"""


# ============================================================================
# 测试 double：TermMixin + 模拟 backend
# ============================================================================


class _TestPlatform(TermMixin):
    """测试 double — 提供 _term_for 返回模拟 backend。"""

    def __init__(self, mock_backend: Mock) -> None:
        self._mock_backend = mock_backend

    def _term_for(self, base_id: str) -> Mock:  # type: ignore[override]
        return self._mock_backend


# ============================================================================
# Mock 构建辅助函数
# ============================================================================


def _make_search_item(
    term_id: str,
    term_name: str,
    term_code: str = "",
    term_type: str = "Concept",
    ext_attrs: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """构建模拟 search_terms 返回的 TermItem 对象。"""
    return SimpleNamespace(
        term_id=term_id,
        term_name=term_name,
        term_code=term_code or term_name,
        term_type=term_type,
        ext_attrs=ext_attrs or {},
    )


def _make_term_detail(
    term_id: str,
    term_name: str,
    term_code: str = "",
    term_type: str = "Concept",
    ext_attrs: dict[str, Any] | None = None,
) -> SimpleNamespace:
    """构建模拟 get_term_detail 返回的 TermDetail 对象。"""
    return SimpleNamespace(
        term_id=term_id,
        term_name=term_name,
        term_code=term_code or term_name,
        term_type=term_type,
        ext_attrs=ext_attrs or {},
    )


def _make_edge(
    source_id: str,
    target_id: str,
    relation_name: str = "part-of",
    depth: int = 1,
    *,
    source_name: str = "",
    target_name: str = "",
    source_code: str = "",
    target_code: str = "",
    source_type: str = "Concept",
    target_type: str = "Concept",
    source_ext_attrs: dict[str, Any] | None = None,
    target_ext_attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建模拟 query_term_relations_tree 返回的关系边。"""
    return {
        "relation_id": f"rel-{source_id}-{target_id}",
        "source_term_id": source_id,
        "target_term_id": target_id,
        "next_term_id": target_id,
        "relation_name": relation_name,
        "relation_category": "ONTOLOGY",
        "direction": "outbound",
        "depth": depth,
        "source_term_name": source_name or f"term-{source_id}",
        "target_term_name": target_name or f"term-{target_id}",
        "source_term_code": source_code or source_id,
        "target_term_code": target_code or target_id,
        "source_term_type": source_type,
        "target_term_type": target_type,
        "source_ext_attrs": source_ext_attrs or {},
        "target_ext_attrs": target_ext_attrs or {},
    }


def _build_platform(mock_backend: Mock | None = None) -> _TestPlatform:
    """创建带 mock backend 的 test double。"""
    if mock_backend is None:
        mock_backend = Mock()
    mock_backend.search_terms.return_value = QueryResult(items=[], total=0)
    mock_backend.get_term_detail.return_value = None
    mock_backend.query_term_relations_tree.return_value = {"data": []}
    return _TestPlatform(mock_backend)


def _fresh_options(profile: str = "graph_fast") -> Any:
    """获取 profile 对应的默认 GraphQueryOptions。"""
    return GRAPH_QUERY_PROFILE_DEFAULTS[profile]


# ============================================================================
# 基础查询测试
# ============================================================================


def test_single_keyword_basic_query() -> None:
    """单个关键词基础查询：搜索 → 详情 → 关系图谱。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("term-001", "byDC", "byDC", "Product")
    backend.search_terms.return_value = QueryResult(items=[item], total=1)

    detail = _make_term_detail("term-001", "byDC", "byDC", "Product", {"kb_id": "78"})
    backend.get_term_detail.return_value = detail

    edge = _make_edge("term-001", "term-002", "part-of", depth=1, target_name="本体库")
    backend.query_term_relations_tree.return_value = {"data": [edge]}

    result = platform.query_knowledge_graph(
        base_id="test", options=_fresh_options("graph_fast"), keywords=["byDC"]
    )

    assert "root_terms" in result
    root_terms = result["root_terms"]
    assert len(root_terms) == 1
    assert root_terms[0]["term_name"] == "byDC"
    assert root_terms[0]["term_code"] == "byDC"
    assert len(root_terms[0]["graph"]) >= 1
    assert "total_terms" in result


def test_batch_keywords_with_deduplication() -> None:
    """批量关键词查询：两个关键词查到同一术语，去重后只保留一个。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("term-001", "byDC", "byDC", "Product")

    call_count = 0

    def search_side_effect(**kwargs: Any) -> QueryResult:
        nonlocal call_count
        call_count += 1
        return QueryResult(items=[item], total=1)

    backend.search_terms.side_effect = search_side_effect

    detail = _make_term_detail("term-001", "byDC", "byDC", "Product")
    backend.get_term_detail.return_value = detail

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options("graph_fast"),
        keywords=["byDC", "百应数据云"],
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1


def test_term_ids_query() -> None:
    """term_ids 精准查询：通过 term_id 直接获取术语详情。"""
    backend = Mock()
    platform = _build_platform(backend)

    detail = _make_term_detail("term-a", "TermA", "termA", "Concept", {"kb_id": "1"})
    backend.get_term_detail.return_value = detail

    result = platform.query_knowledge_graph(
        base_id="test", options=_fresh_options(), term_ids=["term-a"]
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1
    assert root_terms[0]["term_id"] == "term-a"
    assert root_terms[0]["term_name"] == "TermA"


def test_term_ids_skip_duplicates() -> None:
    """term_ids 查询中重复 ID 被跳过。"""
    backend = Mock()
    platform = _build_platform(backend)

    detail = _make_term_detail("term-a", "TermA")
    backend.get_term_detail.return_value = detail

    result = platform.query_knowledge_graph(
        base_id="test", options=_fresh_options(), term_ids=["term-a", "term-a"]
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1


# ============================================================================
# kb_ids 过滤测试
# ============================================================================


def test_kb_ids_filtering_on_search() -> None:
    """kb_ids 过滤：只保留 ext_attrs.kb_id 匹配的搜索结果。"""
    backend = Mock()
    platform = _build_platform(backend)

    matching = _make_search_item(
        "term-001", "本体库", "ontology_repo", "Concept", {"kb_id": "78"}
    )
    non_matching = _make_search_item(
        "term-002", "其他", "other", "Concept", {"kb_id": "99"}
    )
    backend.search_terms.return_value = QueryResult(
        items=[non_matching, matching], total=2
    )

    backend.get_term_detail.return_value = _make_term_detail(
        "term-001", "本体库", "ontology_repo", "Concept", {"kb_id": "78"}
    )

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["本体库"],
        kb_ids={"78"},
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1
    assert root_terms[0]["term_id"] == "term-001"


def test_kb_ids_filtering_excludes_all() -> None:
    """kb_ids 过滤：所有结果都不匹配时返回空。"""
    backend = Mock()
    platform = _build_platform(backend)

    non_matching = _make_search_item(
        "term-002", "其他", "other", "Concept", {"kb_id": "88"}
    )
    backend.search_terms.return_value = QueryResult(items=[non_matching], total=1)

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["其他"],
        kb_ids={"78"},
    )

    assert result["root_terms"] == []
    assert result["total_terms"] == 0


def test_kb_ids_filtering_on_relations() -> None:
    """kb_ids 过滤关系图：只保留 target_ext_attrs.kb_id 匹配的子节点。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("root-1", "根术语", "root", "Concept", {"kb_id": "78"})
    backend.search_terms.return_value = QueryResult(items=[item], total=1)

    detail = _make_term_detail("root-1", "根术语", "root", "Concept", {"kb_id": "78"})
    backend.get_term_detail.return_value = detail

    edges = [
        _make_edge(
            "root-1",
            "child-1",
            "part-of",
            depth=1,
            target_name="匹配子节点",
            target_ext_attrs={"kb_id": "78"},
        ),
        _make_edge(
            "root-1",
            "child-2",
            "part-of",
            depth=1,
            target_name="不匹配子节点",
            target_ext_attrs={"kb_id": "99"},
        ),
    ]
    backend.query_term_relations_tree.return_value = {"data": edges}

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["根术语"],
        kb_ids={"78"},
    )

    root_terms = result["root_terms"]
    graph = root_terms[0]["graph"]
    matched_ids = {node["term_id"] for node in graph}
    assert "child-1" in matched_ids
    assert "child-2" not in matched_ids


# ============================================================================
# 截断与独立 visited 测试
# ============================================================================


def test_max_edges_truncation() -> None:
    """max_edges_per_root 截断：关系图在达到上限后停止。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("root-1", "根术语")
    backend.search_terms.return_value = QueryResult(items=[item], total=1)
    backend.get_term_detail.return_value = _make_term_detail("root-1", "根术语")

    # 生成远多于 max_edges_per_root 的关系边
    many_edges = [
        _make_edge(
            "root-1", f"child-{i}", f"rel-{i}", depth=1, target_name=f"子术语{i}"
        )
        for i in range(50)
    ]
    backend.query_term_relations_tree.return_value = {"data": many_edges}

    # 使用 graph_fast，其 max_edges_per_root = 100（超过 50，不触发截断）
    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options("graph_fast"),
        keywords=["根术语"],
    )

    graph = result["root_terms"][0]["graph"]
    # graph_fast max_edges_per_root=100 > 50 edges, 全部保留
    assert len(graph) == 50


def test_max_edges_truncation_tight_limit() -> None:
    """max_edges_per_root 小值截断时只保留前 N 条边。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("root-1", "根术语")
    backend.search_terms.return_value = QueryResult(items=[item], total=1)
    backend.get_term_detail.return_value = _make_term_detail("root-1", "根术语")

    many_edges = [
        _make_edge(
            "root-1", f"child-{i}", f"rel-{i}", depth=1, target_name=f"子术语{i}"
        )
        for i in range(30)
    ]
    backend.query_term_relations_tree.return_value = {"data": many_edges}

    # Explicitly set max_edges_per_root=5 to trigger truncation
    options = GraphQueryOptions(
        query_profile="graph_fast",
        max_level=1,
        top_k=20,
        max_candidates=5,
        max_edges_per_root=5,
        direction="both",
    )
    result = platform.query_knowledge_graph(
        base_id="test",
        options=options,
        keywords=["根术语"],
    )

    graph = result["root_terms"][0]["graph"]
    # 30 edges generated, but only 5 should be retained due to max_edges_per_root=5
    assert len(graph) == 5


def test_per_root_relation_visited_independence() -> None:
    """每个根术语有独立的 relation_visited，同一子节点可存在于不同根术语图中。"""
    backend = Mock()
    platform = _build_platform(backend)

    item_a = _make_search_item("root-a", "RootA")
    item_b = _make_search_item("root-b", "RootB")

    call = 0

    def search_side_effect(**kwargs: Any) -> QueryResult:
        nonlocal call
        call += 1
        if call == 1:
            return QueryResult(items=[item_a], total=1)
        return QueryResult(items=[item_b], total=1)

    backend.search_terms.side_effect = search_side_effect
    backend.get_term_detail.side_effect = [
        _make_term_detail("root-a", "RootA"),
        _make_term_detail("root-b", "RootB"),
    ]

    def relation_side_effect(**kwargs: Any) -> dict[str, Any]:
        term_id = kwargs.get("term_id", "")
        if term_id == "root-a":
            return {
                "data": [_make_edge("root-a", "shared-term", "relates-to", depth=1)]
            }
        if term_id == "root-b":
            return {
                "data": [_make_edge("root-b", "shared-term", "relates-to", depth=1)]
            }
        return {"data": []}

    backend.query_term_relations_tree.side_effect = relation_side_effect

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["root-a", "root-b"],
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 2

    graph_a = root_terms[0]["graph"]
    graph_b = root_terms[1]["graph"]
    assert any(e["term_id"] == "shared-term" for e in graph_a)
    assert any(e["term_id"] == "shared-term" for e in graph_b)


# ============================================================================
# 消歧测试
# ============================================================================


def test_disambiguation_auto_picks_top1() -> None:
    """disambiguation_mode=auto：每个关键词只取首位匹配术语。"""
    backend = Mock()
    platform = _build_platform(backend)

    items = [
        _make_search_item(
            "term-001", "对象", "object"
        ),  # exact match for keyword "对象"
        _make_search_item("term-002", "对象属性", "property"),
    ]
    backend.search_terms.return_value = QueryResult(items=items, total=2)

    backend.get_term_detail.return_value = _make_term_detail(
        "term-001", "对象", "object"
    )

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["对象"],
        disambiguation_mode="auto",
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1
    assert root_terms[0]["term_id"] == "term-001"


def test_disambiguation_return_all_respects_max_candidates() -> None:
    """disambiguation_mode=return_all + max_candidates 限制返回候选数。"""
    backend = Mock()
    platform = _build_platform(backend)

    items = [_make_search_item(f"term-{i:03d}", f"Term{i}") for i in range(10)]
    backend.search_terms.return_value = QueryResult(items=items, total=10)
    backend.get_term_detail.return_value = _make_term_detail("term-000", "Term0")

    # graph_deep defaults to max_candidates=10, override
    options = _fresh_options("graph_deep")
    result = platform.query_knowledge_graph(
        base_id="test",
        options=options,  # max_candidates=10
        keywords=["Term"],
        disambiguation_mode="return_all",
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 10


def test_exact_match_prioritized_over_fuzzy() -> None:
    """精确匹配优先于模糊匹配：auto 模式选择 exact match 的 top1。"""
    backend = Mock()
    platform = _build_platform(backend)

    # 精确匹配项 + 模糊匹配项混合
    items = [
        _make_search_item("term-001", "模糊项A"),
        _make_search_item("term-002", "byDC", "byDC"),  # 精确匹配关键词
        _make_search_item("term-003", "模糊项B"),
    ]
    backend.search_terms.return_value = QueryResult(items=items, total=3)
    backend.get_term_detail.return_value = _make_term_detail("term-002", "byDC", "byDC")

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["byDC"],
        disambiguation_mode="auto",
    )

    root_terms = result["root_terms"]
    assert len(root_terms) == 1
    assert root_terms[0]["term_id"] == "term-002"


# ============================================================================
# 错误处理测试
# ============================================================================


def test_no_results_returns_empty() -> None:
    """搜索无结果时返回空 root_terms。"""
    backend = Mock()
    platform = _build_platform(backend)

    backend.search_terms.return_value = QueryResult(items=[], total=0)

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["不存在的术语"],
    )

    assert result["root_terms"] == []
    assert result["total_terms"] == 0


def test_term_id_not_found_skipped() -> None:
    """term_ids 查询中不存在的 ID 被跳过。"""
    backend = Mock()
    platform = _build_platform(backend)

    backend.get_term_detail.return_value = None

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        term_ids=["non-existent"],
    )

    assert result["root_terms"] == []
    assert result["total_terms"] == 0


# ============================================================================
# 返回结构验证测试
# ============================================================================


def test_return_structure() -> None:
    """验证返回结构：root_terms / graph / total_terms。"""
    backend = Mock()
    platform = _build_platform(backend)

    items = [
        _make_search_item("term-001", "byDC", "byDC", "Product"),
        _make_search_item("term-002", "本体库", "ontology_repo", "Concept"),
    ]

    call = 0

    def search_side_effect(**kwargs: Any) -> QueryResult:
        nonlocal call
        call += 1
        return QueryResult(items=[items[call - 1]], total=1)

    backend.search_terms.side_effect = search_side_effect
    backend.get_term_detail.side_effect = [
        _make_term_detail("term-001", "byDC", "byDC", "Product"),
        _make_term_detail("term-002", "本体库", "ontology_repo", "Concept"),
    ]

    def relation_side_effect(**kwargs: Any) -> dict[str, Any]:
        term_id = kwargs.get("term_id", "")
        if term_id == "term-001":
            return {
                "data": [_make_edge("term-001", "term-003", depth=1, target_name="子A")]
            }
        if term_id == "term-002":
            return {
                "data": [_make_edge("term-002", "term-004", depth=1, target_name="子B")]
            }
        return {"data": []}

    backend.query_term_relations_tree.side_effect = relation_side_effect

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options(),
        keywords=["byDC", "本体库"],
    )

    assert "root_terms" in result
    assert "total_terms" in result

    root_terms = result["root_terms"]
    assert len(root_terms) == 2

    for rt in root_terms:
        assert "term_id" in rt
        assert "term_name" in rt
        assert "term_code" in rt
        assert "term_type" in rt
        assert "attributes" in rt
        assert "graph" in rt
        assert "depth" in rt
        assert "max_depth" in rt
        assert "seg" in rt

        for node in rt["graph"]:
            assert "term_id" in node
            assert "term_name" in node
            assert "path" in node
            assert "depth" in node
            assert "seg" in node

    assert result["total_terms"] >= len(root_terms)


def test_max_depth_zero_when_no_relations() -> None:
    """无关系时 max_depth=0 且 graph 为空列表。"""
    backend = Mock()
    platform = _build_platform(backend)

    item = _make_search_item("term-001", "byDC", "byDC", "Product")
    backend.search_terms.return_value = QueryResult(items=[item], total=1)
    backend.get_term_detail.return_value = _make_term_detail(
        "term-001", "byDC", "byDC", "Product"
    )

    result = platform.query_knowledge_graph(
        base_id="test",
        options=_fresh_options("graph_fast"),
        keywords=["byDC"],
    )

    rt = result["root_terms"][0]
    assert rt["max_depth"] == 0
    assert rt["graph"] == []
    assert result["total_terms"] == 1
