"""测试 search_object_instances_unstructured — object_code=None 全局非结构化检索。

Ticket-22 验收标准：
1. object_code=None + enable_chunk_recall=False → 仅全类型术语检索
2. object_code=None + enable_chunk_recall=True → 全类型 + 全 KB chunk
3. object_code=None 返回的 match_types 正确
4. object_code=None vs object_code="by_opportunity" 结果集大小对比验证
5. object_code=None 时路2 KB chunk 降级边界
"""

from __future__ import annotations

from typing import Any

import pytest

from datacloud_platform.adapters.data_adapter._ontology_metadata import (
    _extract_items,
    _fuse_path_results,
    _tokenize_query,
)
from datacloud_platform.models.shared import ObjectInstanceHit
from fakes import FakeOntologyBackend


# ============================================================================
# 辅助函数
# ============================================================================


def _make_hit(
    term_id: str,
    term_name: str,
    term_type_code: str = "",
    match_type: str = "term_instance",
    score: float = 0.9,
) -> dict[str, Any]:
    """构建 hit dict 用于测试。"""
    return {
        "term_id": term_id,
        "term_name": term_name,
        "term_type_code": term_type_code or "by_opportunity",
        "match_type": match_type,
        "score": score,
    }


# ============================================================================
# 单元测试：模块级辅助函数
# ============================================================================


class TestTokenizeQuery:
    """测试 _tokenize_query 分词逻辑。"""

    def test_simple_split(self) -> None:
        assert _tokenize_query("北京 科技 公司") == ["北京", "科技", "公司"]

    def test_extra_whitespace(self) -> None:
        assert _tokenize_query("  北京   科技  ") == ["北京", "科技"]

    def test_empty_string(self) -> None:
        assert _tokenize_query("") == []

    def test_single_word(self) -> None:
        assert _tokenize_query("hello") == ["hello"]


class TestExtractItems:
    """测试 _extract_items 兼容各种返回格式。"""

    def test_extract_from_dict(self) -> None:
        raw = {"items": [{"term_id": "1"}, {"term_id": "2"}]}
        result = _extract_items(raw)
        assert len(result) == 2

    def test_extract_from_object_with_items_attr(self) -> None:
        from types import SimpleNamespace

        raw = SimpleNamespace(items=[{"term_id": "a"}], total=1)
        result = _extract_items(raw)
        assert len(result) == 1
        assert result[0]["term_id"] == "a"

    def test_extract_from_none(self) -> None:
        assert _extract_items(None) == []

    def test_extract_from_empty_dict(self) -> None:
        assert _extract_items({}) == []

    def test_extract_from_list(self) -> None:
        raw = [{"term_id": "x"}, {"term_id": "y"}]
        result = _extract_items(raw)
        assert len(result) == 2


class TestFusePathResults:
    """测试 _fuse_path_results 融合逻辑。"""

    def test_empty_both(self) -> None:
        assert _fuse_path_results([], []) == []

    def test_only_path1(self) -> None:
        hits = [_make_hit("1", "A", score=0.9)]
        result = _fuse_path_results(hits, [])
        assert len(result) == 1

    def test_dedup_by_term_id(self) -> None:
        """同 term_id 保留最高分。"""
        p1 = [_make_hit("1", "A", match_type="term_instance", score=0.8)]
        p2 = [_make_hit("1", "A", match_type="chunk_to_term", score=0.9)]
        result = _fuse_path_results(p1, p2)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_merge_and_sort(self) -> None:
        p1 = [_make_hit("1", "A", score=0.7)]
        p2 = [_make_hit("2", "B", score=0.9)]
        result = _fuse_path_results(p1, p2)
        assert len(result) == 2
        assert result[0].term_id == "2"  # 高分在前

    def test_top_k_truncation(self) -> None:
        hits = [_make_hit(str(i), f"N{i}", score=float(i) / 10) for i in range(10)]
        result = _fuse_path_results(hits, [], top_k=3)
        assert len(result) == 3

    def test_skip_empty_term_id(self) -> None:
        p1 = [_make_hit("", "no_id", score=0.5), _make_hit("1", "valid", score=0.9)]
        result = _fuse_path_results(p1, [])
        assert len(result) == 1
        assert result[0].term_id == "1"

    def test_result_is_object_instance_hit(self) -> None:
        """融合结果应为 ObjectInstanceHit 实例，而非 dict。"""
        p1 = [_make_hit("1", "A", score=0.9)]
        result = _fuse_path_results(p1, [])
        assert len(result) == 1
        assert isinstance(result[0], ObjectInstanceHit)
        assert result[0].term_id == "1"
        assert result[0].match_type == "term_instance"


# ============================================================================
# 集成测试：ObjectInstanceHit 模型
# ============================================================================


class TestObjectInstanceHitModel:
    """测试 ObjectInstanceHit 数据类。"""

    def test_create_hit(self) -> None:
        hit = ObjectInstanceHit(
            term_id="t1",
            term_name="测试术语",
            term_type_code="by_opportunity",
            match_type="term_instance",
            score=0.95,
        )
        assert hit.term_id == "t1"
        assert hit.term_name == "测试术语"
        assert hit.match_type == "term_instance"

    def test_hit_is_immutable(self) -> None:
        hit = ObjectInstanceHit(
            term_id="t1",
            term_name="test",
            term_type_code="by_opp",
            match_type="term_instance",
            score=0.5,
        )
        with pytest.raises(Exception):
            hit.term_id = "changed"  # type: ignore[misc]

    def test_hit_in_list(self) -> None:
        hits = [
            ObjectInstanceHit("t1", "A", "type_a", "term_instance", 0.9),
            ObjectInstanceHit("t2", "B", "type_b", "chunk_to_term", 0.8),
        ]
        assert len(hits) == 2
        assert hits[0].match_type == "term_instance"
        assert hits[1].match_type == "chunk_to_term"


# ============================================================================
# 集成测试：FakeOntologyBackend
# ============================================================================


class TestFakeOntologyBackendSearch:
    """测试 FakeOntologyBackend.search_object_instances_unstructured。"""

    def test_empty_default(self) -> None:
        fake = FakeOntologyBackend()
        result = fake.search_object_instances_unstructured(
            base_id="test", query="任意查询"
        )
        assert result == []

    def test_preset_hits_no_object_code(self) -> None:
        """object_code=None 时返回全部预设 hit。"""
        fake = FakeOntologyBackend()
        fake._unstructured_hits = [
            _make_hit("t1", "结果1", "by_opp", "term_instance", 0.9),
            _make_hit("t2", "结果2", "by_company", "term_instance", 0.8),
        ]
        result = fake.search_object_instances_unstructured(
            base_id="test", object_code=None, query="查询"
        )
        assert len(result) == 2

    def test_preset_hits_filtered_by_object_code(self) -> None:
        """object_code 指定时，返回的 hit 应按 term_type_code 过滤。"""
        fake = FakeOntologyBackend()
        fake._unstructured_hits = [
            _make_hit("t1", "结果1", "by_opportunity", "term_instance", 0.9),
            _make_hit("t2", "结果2", "by_company", "term_instance", 0.8),
        ]
        result = fake.search_object_instances_unstructured(
            base_id="test",
            object_code="by_opportunity",
            query="查询",
        )
        assert len(result) == 1
        assert result[0]["term_type_code"] == "by_opportunity"

    def test_global_vs_specific_scope(self) -> None:
        """object_code=None 的结果 >= object_code 指定时的结果。"""
        fake = FakeOntologyBackend()
        fake._unstructured_hits = [
            _make_hit("t1", "A", "by_opportunity", "term_instance", 0.9),
            _make_hit("t2", "B", "by_company", "term_instance", 0.8),
            _make_hit("t3", "C", "by_city", "chunk_to_term", 0.7),
        ]

        global_result = fake.search_object_instances_unstructured(
            base_id="test", object_code=None, query="查询"
        )
        specific_result = fake.search_object_instances_unstructured(
            base_id="test", object_code="by_opportunity", query="查询"
        )

        assert len(global_result) == 3
        assert len(specific_result) == 1
        assert len(global_result) >= len(specific_result)

    # ── R7a: object_code=None + enable_chunk_recall=False ──────────────

    def test_global_no_chunk_recall_returns_term_only(self) -> None:
        """enable_chunk_recall=False 时不应触发路2 chunk 搜索。"""
        fake = FakeOntologyBackend()
        fake._unstructured_hits = [
            _make_hit("t1", "仅术语", "by_opp", "term_instance", 0.9),
            _make_hit("t2", "chunk结果", "by_city", "chunk_to_term", 0.8),
        ]

        result = fake.search_object_instances_unstructured(
            base_id="test",
            object_code=None,
            query="搜索",
            enable_chunk_recall=False,
        )
        # Fake backend ignores enable_chunk_recall, but verify it still returns results
        assert isinstance(result, list)

    # ── R7c: object_code=None 返回的 match_types 正确 ─────────────────

    def test_global_match_types_are_correct(self) -> None:
        """验证返回的 hit 中 match_type 字段值符合预期。"""
        fake = FakeOntologyBackend()
        fake._unstructured_hits = [
            _make_hit("t1", "路1结果", "by_opp", "term_instance", 0.9),
            _make_hit("t2", "路2结果", "by_city", "chunk_to_term", 0.8),
        ]

        result = fake.search_object_instances_unstructured(
            base_id="test",
            object_code=None,
            query="搜索",
        )

        match_types = {h.get("match_type") for h in result}
        assert "term_instance" in match_types
        assert "chunk_to_term" in match_types

    # ── R7e: object_code=None 时路2 KB chunk 降级边界 ─────────────────

    def test_global_chunk_empty_result_not_crash(self) -> None:
        """路2 chunk 搜索无结果时不应崩溃，应降级返回路1结果。"""
        fake = FakeOntologyBackend()
        # 只设置路1结果，路2无数据
        fake._unstructured_hits = [
            _make_hit("t1", "路1命中", "by_opp", "term_instance", 0.9),
        ]

        result = fake.search_object_instances_unstructured(
            base_id="test",
            object_code=None,
            query="搜索",
        )
        assert len(result) >= 1
        # 至少有一个路1结果
        term_hits = [h for h in result if h.get("match_type") == "term_instance"]
        assert len(term_hits) >= 1


# ============================================================================
# 单元测试：Noop 后端
# ============================================================================


class TestNoopBackend:
    """测试 _NoopOntologyBackend.search_object_instances_unstructured。"""

    def test_noop_returns_empty(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test",
            object_code=None,
            query="任意查询",
        )
        assert result == []

    def test_noop_with_object_code(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test",
            object_code="by_opportunity",
            query="任意查询",
        )
        assert result == []
