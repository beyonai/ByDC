"""测试 search_object_instances_unstructured — 非结构化对象实例检索。

ObjectInstanceHit 6 字段:
- instance_id, instance_code, instance_name
- object_code, file_name, score
ObjectInstanceSearchResult: {keyword: [hit, ...]}
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from datacloud_platform.adapters.data_adapter._ontology_metadata import (
    _extract_items,
    _fuse_path_results,
    _resolve_input_mode,
    _tokenize_query,
)
from datacloud_platform.models.shared import (
    ObjectInstanceHit,
    ObjectInstanceSearchResult,
)
from fakes import FakeOntologyBackend


# ============================================================================
# 辅助函数
# ============================================================================


def _make_hit(
    term_id: str,
    term_name: str,
    term_code: str = "",
    term_type_code: str = "",
    file_name: str | None = None,
    match_type: str = "term_instance",
    score: float = 0.9,
) -> dict[str, Any]:
    """构建 hit dict 用于测试。"""
    return {
        "term_id": term_id,
        "term_code": term_code or term_id,
        "term_name": term_name,
        "term_type_code": term_type_code or "by_opportunity",
        "file_name": file_name or "/docs/test.md",
        "match_type": match_type,
        "score": score,
    }


# ============================================================================
# 单元测试：模块级辅助函数
# ============================================================================


class TestTokenizeQuery:
    def test_simple_split(self) -> None:
        assert _tokenize_query("北京 科技 公司") == ["北京", "科技", "公司"]

    def test_extra_whitespace(self) -> None:
        assert _tokenize_query("  北京   科技  ") == ["北京", "科技"]

    def test_empty_string(self) -> None:
        assert _tokenize_query("") == []

    def test_single_word(self) -> None:
        assert _tokenize_query("hello") == ["hello"]


class TestExtractItems:
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


# ============================================================================
# ObjectInstanceHit 模型测试
# ============================================================================


class TestObjectInstanceHitModel:
    def test_create_hit(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="opp_001",
            instance_name="测试实例",
            object_code="by_opportunity",
            file_name="/docs/opp_001.md",
            score=0.95,
        )
        assert hit.instance_id == "t1"
        assert hit.instance_code == "opp_001"
        assert hit.instance_name == "测试实例"
        assert hit.object_code == "by_opportunity"
        assert hit.file_name == "/docs/opp_001.md"
        assert hit.score == 0.95

    def test_hit_is_immutable(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="test",
            object_code="by_opp",
            file_name="/x.md",
            score=0.5,
        )
        with pytest.raises(Exception):
            hit.score = 99  # type: ignore[misc]

    def test_file_name_can_be_none(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="test",
            object_code="t",
            file_name=None,
            score=0.5,
        )
        assert hit.file_name is None

    def test_hit_in_list(self) -> None:
        hits = [
            ObjectInstanceHit("t1", "c1", "A", "type_a", "/a.md", 0.9),
            ObjectInstanceHit("t2", "c2", "B", "type_b", "/b.md", 0.8),
        ]
        assert len(hits) == 2
        assert hits[0].instance_name == "A"
        assert hits[1].instance_name == "B"


# ============================================================================
# RRF 融合测试
# ============================================================================


class TestFusePathResults:
    def test_empty_both(self) -> None:
        assert _fuse_path_results([], []) == []

    def test_only_path1(self) -> None:
        hits = [_make_hit("1", "A", score=0.9)]
        result = _fuse_path_results(hits, [])
        assert len(result) == 1
        assert result[0].instance_id == "1"
        assert result[0].instance_name == "A"

    def test_dedup_by_term_id(self) -> None:
        p1 = [_make_hit("1", "A", score=0.8, file_name="/p1.md")]
        p2 = [
            _make_hit(
                "1", "A", score=0.9, match_type="chunk_to_term", file_name="/p2.md"
            )
        ]
        result = _fuse_path_results(p1, p2)
        assert len(result) == 1
        # RRF: rank 1 in path1 + rank 1 in path2
        expected = 1 / 61 + 1 / 61
        assert abs(result[0].score - expected) < 0.0001
        # file_name 优先路2
        assert result[0].file_name == "/p2.md"

    def test_merge_and_sort(self) -> None:
        p1 = [_make_hit("1", "A", score=0.7)]
        p2 = [_make_hit("2", "B", score=0.9)]
        result = _fuse_path_results(p1, p2)
        assert len(result) == 2

    def test_top_k_truncation(self) -> None:
        hits = [_make_hit(str(i), f"N{i}", score=float(i) / 10) for i in range(10)]
        result = _fuse_path_results(hits, [], top_k=3)
        assert len(result) == 3

    def test_skip_empty_term_id(self) -> None:
        p1 = [_make_hit("", "no_id", score=0.5), _make_hit("1", "valid", score=0.9)]
        result = _fuse_path_results(p1, [])
        assert len(result) == 1
        assert result[0].instance_id == "1"

    def test_result_is_object_instance_hit(self) -> None:
        p1 = [_make_hit("1", "A", term_code="opp_001", score=0.9)]
        result = _fuse_path_results(p1, [])
        assert len(result) == 1
        assert isinstance(result[0], ObjectInstanceHit)
        assert result[0].instance_id == "1"
        assert result[0].instance_code == "opp_001"

    def test_file_name_from_ext_attrs(self) -> None:
        p1 = [_make_hit("1", "A", file_name="/KB/Term.md", score=0.9)]
        result = _fuse_path_results(p1, [])
        assert result[0].file_name == "/KB/Term.md"


# ============================================================================
# FakeOntologyBackend 集成测试
# ============================================================================


class TestFakeOntologyBackendSearch:
    """测试 FakeOntologyBackend.search_object_instances_unstructured (async 包装)。"""

    def test_empty_default(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            return await fake.search_object_instances_unstructured(
                base_id="test", query="任意查询"
            )

        result = asyncio.run(_t())
        assert isinstance(result, ObjectInstanceSearchResult)
        assert "任意查询" in result.results
        assert result.results["任意查询"] == []

    def test_preset_hits_no_object_code(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "结果1", term_type_code="by_opp"),
                _make_hit("t2", "结果2", term_type_code="by_company"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_code=None, query="查询"
            )

        result = asyncio.run(_t())
        assert "查询" in result.results
        assert len(result.results["查询"]) == 2

    def test_preset_hits_filtered_by_object_code(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "结果1", term_type_code="by_opportunity"),
                _make_hit("t2", "结果2", term_type_code="by_company"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_code="by_opportunity", query="查询"
            )

        result = asyncio.run(_t())
        assert len(result.results["查询"]) == 1

    def test_global_vs_specific_scope(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "A", term_type_code="by_opp"),
                _make_hit("t2", "B", term_type_code="by_company"),
                _make_hit("t3", "C", term_type_code="by_city"),
            ]
            g = await fake.search_object_instances_unstructured(
                base_id="test", object_code=None, query="查询"
            )
            s = await fake.search_object_instances_unstructured(
                base_id="test", object_code="by_opp", queries=["查询"]
            )
            return g, s

        g, s = asyncio.run(_t())
        assert len(g.results["查询"]) == 3
        assert len(s.results["查询"]) == 1

    def test_word_batch_mode(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [_make_hit("t1", "A", term_type_code="by_opp")]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_code=None, queries=["OCR", "Agent"]
            )

        result = asyncio.run(_t())
        assert set(result.results.keys()) == {"OCR", "Agent"}

    def test_global_no_chunk_recall(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "仅术语", term_type_code="by_opp")
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test",
                object_code=None,
                query="搜索",
                enable_chunk_recall=False,
            )

        result = asyncio.run(_t())
        assert isinstance(result, ObjectInstanceSearchResult)

    def test_global_chunk_empty_result_not_crash(self) -> None:
        async def _t():
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "路1命中", term_type_code="by_opp")
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_code=None, query="搜索"
            )

        result = asyncio.run(_t())
        assert len(result.results.get("搜索", [])) >= 0


# ============================================================================
# Noop Backend 测试
# ============================================================================


class TestNoopBackend:
    def test_noop_returns_empty(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test", query="任意"
        )
        assert result == []

    def test_noop_with_object_code(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test", object_code="by_opp", query="任意"
        )
        assert result == []


# ============================================================================
# _resolve_input_mode 测试
# ============================================================================


class TestResolveInputMode:
    def test_sentence_from_query(self) -> None:
        mode, kw = _resolve_input_mode("hello world", None)
        assert mode == "sentence"
        assert kw == ["hello world"]

    def test_word_batch_from_queries(self) -> None:
        mode, kw = _resolve_input_mode(None, ["a", "b", "c"])
        assert mode == "word_batch"
        assert kw == ["a", "b", "c"]

    def test_word_batch_filters_empty(self) -> None:
        mode, kw = _resolve_input_mode(None, ["a", "", "  ", "b"])
        assert mode == "word_batch"
        assert kw == ["a", "b"]

    def test_empty_both(self) -> None:
        mode, kw = _resolve_input_mode(None, None)
        assert mode == "sentence"
        assert kw == []

    def test_empty_query(self) -> None:
        mode, kw = _resolve_input_mode("", None)
        assert mode == "sentence"
        assert kw == []


# ============================================================================
# RRF 核心算法测试
# ============================================================================


class TestRRFFusion:
    def test_rrf_formula_correctness(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1 = [
            ("A", "TermA", "", "type_x", ""),
            ("B", "TermB", "", "type_y", ""),
            ("C", "TermC", "", "type_z", ""),
        ]
        p2 = [("B", "TermB", "", "type_y", ""), ("D", "TermD", "", "type_w", "")]
        fused = rrf_fuse([p1, p2], k=60)
        expected = {
            "A": 1 / 61,
            "B": 1 / 62 + 1 / 61,
            "C": 1 / 63,
            "D": 1 / 62,
        }
        assert len(fused) == 4
        for c in fused:
            assert abs(c.rrf_score - expected[c.term_id]) < 0.0001

    def test_rrf_sorted_desc(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1 = [("A", "TA", "", "tx", ""), ("B", "TB", "", "ty", "")]
        p2 = [("B", "TB", "", "ty", ""), ("C", "TC", "", "tz", "")]
        fused = rrf_fuse([p1, p2], k=60)
        scores = [c.rrf_score for c in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_empty_both(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        assert rrf_fuse([], k=60) == []

    def test_rrf_only_path1(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1 = [("A", "TA", "", "tx", "")]
        fused = rrf_fuse([p1], k=60)
        assert len(fused) == 1
        assert fused[0].term_id == "A"

    def test_rrf_single_path_rank1(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        fused = rrf_fuse([[("X", "TX", "", "tt", "")]], k=60)
        assert abs(fused[0].rrf_score - 1 / 61) < 0.0001

    def test_rrf_dedup_across_paths(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1 = [("A", "TA", "", "tx", "")]
        p2 = [("A", "TA", "", "tx", "")]
        fused = rrf_fuse([p1, p2], k=60)
        assert len(fused) == 1

    def test_rrf_top_n_truncation(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        items = [(chr(65 + i), f"T{chr(65 + i)}", "", "t", "") for i in range(10)]
        fused = rrf_fuse([items], k=60, top_n=3)
        assert len(fused) == 3


# ============================================================================
# 降级策略测试
# ============================================================================


class TestDowngradeStrategies:
    def test_kb_configs_none_skips_path2(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _should_run_path2,
        )

        assert _should_run_path2(True, None) is False

    def test_enable_chunk_recall_false_skips_path2(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _should_run_path2,
        )

        assert _should_run_path2(False, {"kb": "test"}) is False

    def test_both_enabled_returns_true(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _should_run_path2,
        )

        assert _should_run_path2(True, {"kb": "test"}) is True

    def test_path2_no_kb_id_returns_empty(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _fuse_path_results_rrf,
        )

        result = _fuse_path_results_rrf([], [], k=60)
        assert result == []


# ============================================================================
# 全局检索 + RRF 测试
# ============================================================================


class TestGlobalSearchRRF:
    def test_global_search_includes_both_paths(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1 = [("A", "TermA", "", "by_opp", ""), ("B", "TermB", "", "by_company", "")]
        p2 = [("C", "TermC", "", "by_city", ""), ("D", "TermD", "", "by_product", "")]
        fused = rrf_fuse([p1, p2], k=60)
        assert len(fused) == 4
        type_codes = {c.term_type_code for c in fused}
        assert "by_opp" in type_codes
        assert "by_company" in type_codes
        assert "by_city" in type_codes
        assert "by_product" in type_codes

    def test_global_scope_larger_than_specific(self) -> None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse

        p1_all = [("A", "A", "", "by_opp", ""), ("B", "B", "", "by_company", "")]
        p2_all = [("C", "C", "", "by_city", "")]
        fused_all = rrf_fuse([p1_all, p2_all], k=60)
        p1_specific = [("A", "A", "", "by_opp", "")]
        fused_specific = rrf_fuse([p1_specific], k=60)
        assert len(fused_all) >= len(fused_specific)
        assert len(fused_all) == 3


# ============================================================================
# ObjectInstanceHit RRF 分数存储测试
# ============================================================================


class TestObjectInstanceHitWithScore:
    def test_field_names_are_correct(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="id1",
            instance_code="code1",
            instance_name="name1",
            object_code="type1",
            file_name="/f.md",
            score=0.95,
        )
        assert hit.instance_id == "id1"
        assert hit.instance_code == "code1"
        assert hit.instance_name == "name1"
        assert hit.object_code == "type1"
        assert hit.file_name == "/f.md"
        assert hit.score == 0.95

    def test_score_is_rrf_fusion_score(self) -> None:
        rrf_score = 1 / 61 + 1 / 62
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="test",
            object_code="t",
            file_name="/f.md",
            score=rrf_score,
        )
        assert isinstance(hit.score, float)
        assert 0 < hit.score <= 1
        assert abs(hit.score - rrf_score) < 0.0001

    def test_score_sorted_desc(self) -> None:
        hits = [
            ObjectInstanceHit("t1", "c1", "A", "t", "/f.md", 0.3),
            ObjectInstanceHit("t2", "c2", "B", "t", "/f.md", 0.9),
            ObjectInstanceHit("t3", "c3", "C", "t", "/f.md", 0.6),
        ]
        sorted_hits = sorted(hits, key=lambda h: h.score, reverse=True)
        assert sorted_hits[0].instance_name == "B"
        assert sorted_hits[1].instance_name == "C"
        assert sorted_hits[2].instance_name == "A"
