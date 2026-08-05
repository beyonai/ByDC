"""测试 search_object_instances_unstructured — 非结构化对象实例检索。

ObjectInstanceHit 8 字段:
- instance_id, instance_code, instance_name
- object_code, file_name, kb_resource_id, kb_id, score
ObjectInstanceSearchResult: {keyword: [hit, ...]}
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from datacloud_platform.adapters.data_adapter._ontology_metadata import (
    OntologyMetadataMixin,
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
            kb_resource_id=None,
            kb_id=None,
            score=0.95,
        )
        assert hit.instance_id == "t1"
        assert hit.instance_code == "opp_001"
        assert hit.instance_name == "测试实例"
        assert hit.object_code == "by_opportunity"
        assert hit.file_name == "/docs/opp_001.md"
        assert hit.kb_resource_id is None
        assert hit.kb_id is None
        assert hit.score == 0.95

    def test_hit_is_immutable(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="test",
            object_code="by_opp",
            file_name="/x.md",
            kb_resource_id=None,
            kb_id=None,
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
            kb_resource_id=None,
            kb_id=None,
            score=0.5,
        )
        assert hit.file_name is None

    def test_hit_with_kb_resource_id(self) -> None:
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="带KB资源",
            object_code="by_opportunity",
            file_name="/docs/kb.md",
            kb_resource_id="kb_res_001",
            kb_id="kb_123",
            score=0.95,
        )
        assert hit.kb_resource_id == "kb_res_001"
        assert hit.kb_id == "kb_123"

    def test_hit_in_list(self) -> None:
        hits = [
            ObjectInstanceHit("t1", "c1", "A", "type_a", "/a.md", None, None, 0.9),
            ObjectInstanceHit("t2", "c2", "B", "type_b", "/b.md", None, None, 0.8),
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
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            return await fake.search_object_instances_unstructured(
                base_id="test", query="任意查询"
            )

        result = asyncio.run(_t())
        assert isinstance(result, ObjectInstanceSearchResult)
        assert "任意查询" in result.results
        assert result.results["任意查询"] == []

    def test_preset_hits_no_object_code(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "结果1", term_type_code="by_opp"),
                _make_hit("t2", "结果2", term_type_code="by_company"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_codes=None, query="查询"
            )

        result = asyncio.run(_t())
        assert "查询" in result.results
        assert len(result.results["查询"]) == 2

    def test_preset_hits_filtered_by_object_codes(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "结果1", term_type_code="by_opportunity"),
                _make_hit("t2", "结果2", term_type_code="by_company"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_codes=["by_opportunity"], query="查询"
            )

        result = asyncio.run(_t())
        assert len(result.results["查询"]) == 1

    def test_object_codes_multiple_types(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "A", term_type_code="Ability"),
                _make_hit("t2", "B", term_type_code="ArticleAnalysis"),
                _make_hit("t3", "C", term_type_code="OtherType"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test",
                object_codes=["Ability", "ArticleAnalysis"],
                query="查询",
            )

        result = asyncio.run(_t())
        assert len(result.results["查询"]) == 2

    def test_object_codes_empty_list(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "A", term_type_code="by_opp"),
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_codes=[], query="查询"
            )

        result = asyncio.run(_t())
        assert isinstance(result, ObjectInstanceSearchResult)
        assert result.results == {}

    def test_global_vs_specific_scope(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "A", term_type_code="by_opp"),
                _make_hit("t2", "B", term_type_code="by_company"),
                _make_hit("t3", "C", term_type_code="by_city"),
            ]
            g = await fake.search_object_instances_unstructured(
                base_id="test", object_codes=None, query="查询"
            )
            s = await fake.search_object_instances_unstructured(
                base_id="test", object_codes=["by_opp"], queries=["查询"]
            )
            return g, s

        g, s = asyncio.run(_t())
        assert len(g.results["查询"]) == 3
        assert len(s.results["查询"]) == 1

    def test_word_batch_mode(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [_make_hit("t1", "A", term_type_code="by_opp")]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_codes=None, queries=["OCR", "Agent"]
            )

        result = asyncio.run(_t())
        assert set(result.results.keys()) == {"OCR", "Agent"}

    def test_global_no_chunk_recall(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "仅术语", term_type_code="by_opp")
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test",
                object_codes=None,
                query="搜索",
                enable_chunk_recall=False,
            )

        result = asyncio.run(_t())
        assert isinstance(result, ObjectInstanceSearchResult)

    def test_global_chunk_empty_result_not_crash(self) -> None:
        async def _t() -> Any:
            fake = FakeOntologyBackend()
            fake._unstructured_hits = [
                _make_hit("t1", "路1命中", term_type_code="by_opp")
            ]
            return await fake.search_object_instances_unstructured(
                base_id="test", object_codes=None, query="搜索"
            )

        result = asyncio.run(_t())
        assert len(result.results.get("搜索", [])) >= 0


# ============================================================================
# Noop Backend 测试
# ============================================================================


class TestNoopBackend:
    def test_noop_returns_empty(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend
        from datacloud_platform.models.shared import ObjectInstanceSearchResult

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test", query="任意"
        )
        assert isinstance(result, ObjectInstanceSearchResult)
        assert result.results == {}

    def test_noop_with_object_codes(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopOntologyBackend
        from datacloud_platform.models.shared import ObjectInstanceSearchResult

        backend = _NoopOntologyBackend()
        result = backend.search_object_instances_unstructured(
            base_id="test", object_codes=["by_opp"], query="任意"
        )
        assert isinstance(result, ObjectInstanceSearchResult)
        assert result.results == {}


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
    def test_enable_chunk_recall_false_skips_path2(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _should_run_path2,
        )

        assert _should_run_path2(False) is False

    def test_enable_chunk_recall_true_allows_path2(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _should_run_path2,
        )

        assert _should_run_path2(True) is True

    def test_path2_no_kb_id_returns_empty(self) -> None:
        from datacloud_platform.adapters.data_adapter._ontology_metadata import (
            _fuse_path_results_rrf,
        )

        result = _fuse_path_results_rrf([], [], k=60)
        assert result == []


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
            kb_resource_id=None,
            kb_id=None,
            score=0.95,
        )
        assert hit.instance_id == "id1"
        assert hit.instance_code == "code1"
        assert hit.instance_name == "name1"
        assert hit.object_code == "type1"
        assert hit.file_name == "/f.md"
        assert hit.kb_resource_id is None
        assert hit.kb_id is None
        assert hit.score == 0.95

    def test_score_is_rrf_fusion_score(self) -> None:
        rrf_score = 1 / 61 + 1 / 62
        hit = ObjectInstanceHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="test",
            object_code="t",
            file_name="/f.md",
            kb_resource_id=None,
            kb_id=None,
            score=rrf_score,
        )
        assert isinstance(hit.score, float)
        assert 0 < hit.score <= 1
        assert abs(hit.score - rrf_score) < 0.0001

    def test_score_sorted_desc(self) -> None:
        hits = [
            ObjectInstanceHit("t1", "c1", "A", "t", "/f.md", None, None, 0.3),
            ObjectInstanceHit("t2", "c2", "B", "t", "/f.md", None, None, 0.9),
            ObjectInstanceHit("t3", "c3", "C", "t", "/f.md", None, None, 0.6),
        ]
        sorted_hits = sorted(hits, key=lambda h: h.score, reverse=True)
        assert sorted_hits[0].instance_name == "B"
        assert sorted_hits[1].instance_name == "C"
        assert sorted_hits[2].instance_name == "A"


def test_resolve_kb_resource_id_for_object_ignores_legacy_kb_id() -> None:
    from datacloud_platform.adapters.data_adapter._ontology_metadata import (
        _resolve_kb_resource_id_for_object,
    )

    assert (
        _resolve_kb_resource_id_for_object(
            {
                "ext_property": {
                    "kb_resource_id": "1234567890",
                    "kb_id": "legacy-internal-id",
                }
            }
        )
        == "1234567890"
    )
    assert (
        _resolve_kb_resource_id_for_object(
            {"ext_property": {"kb_id": "legacy-internal-id"}}
        )
        is None
    )


@pytest.mark.asyncio
async def test_chunk_search_passes_kb_resource_id_to_backend() -> None:
    from datacloud_data_sdk.executor.kb_search_backend import KnowledgeSearchResult
    from datacloud_platform.adapters.data_adapter._ontology_metadata import (
        _do_chunk_search,
    )

    class CapturingBackend:
        request: Any = None

        async def search(self, request: Any) -> KnowledgeSearchResult:
            self.request = request
            return KnowledgeSearchResult(records=[], total=0)

    backend = CapturingBackend()
    await _do_chunk_search(
        query="年假",
        kb_resource_id="1234567890",
        top_k=5,
        _kb_search_backend=backend,
    )

    assert backend.request is not None
    assert backend.request.kb_resource_id == "1234567890"
    assert not hasattr(backend.request, "kb_id")


@pytest.mark.asyncio
async def test_chunk_search_rejects_missing_kb_resource_id() -> None:
    from datacloud_platform.adapters.data_adapter._ontology_metadata import (
        _do_chunk_search,
    )

    with pytest.raises(ValueError, match="kb_resource_id is required"):
        await _do_chunk_search(
            query="年假",
            kb_resource_id="",
            top_k=5,
        )


# ============================================================================
# T-40: _do_path2 多 KB chunk 搜索并发化
# ============================================================================


class TestDoPath2ConcurrentSearch:
    """T-40: _do_path2 内部多 KB chunk 搜索并发执行。

    验收点:
    1. 多 KB 并发：一个成功一个抛异常 → 成功结果正常返回、失败仅告警
    2. 保序合并：合并顺序与 kb_info 迭代顺序一致（gather 保序）
    3. 去重保持：跨 KB 相同 term_id 只保留首个
    """

    @staticmethod
    def _make_adapter() -> OntologyMetadataMixin:
        """创建不执行 __init__ 的裸 adapter（_do_path2 只需 _do_chunk_search）。"""
        return OntologyMetadataMixin.__new__(OntologyMetadataMixin)

    @staticmethod
    def _kb_info() -> dict[str, dict[str, Any]]:
        return {
            "kb_1": {"kb_directory": "/dir1", "object_codes": ["obj_a"]},
            "kb_2": {"kb_directory": "/dir2", "object_codes": ["obj_b"]},
        }

    @pytest.mark.asyncio
    async def test_one_kb_fails_one_succeeds(self) -> None:
        """一个 KB 抛异常 → 仅告警降级；另一个 KB 结果正常返回。"""
        adapter = self._make_adapter()
        attempted: list[str] = []

        async def fake_chunk_search(
            *,
            query: str,
            kb_resource_id: str | None,
            top_k: int,
            kb_directory: str | None = None,
            term_type_codes: list[str] | None = None,
            **_: Any,
        ) -> list[dict[str, Any]]:
            attempted.append(kb_resource_id or "")
            if kb_resource_id == "kb_1":
                raise RuntimeError("kb_1 backend down")
            return [{"term_id": "tid_ok", "term_code": "c_ok", "score": 0.9}]

        adapter._do_chunk_search = fake_chunk_search  # type: ignore[method-assign]

        with patch(
            "datacloud_platform.adapters.data_adapter._ontology_metadata.logger"
        ) as mock_logger:
            result = await adapter._do_path2(
                self._kb_info(), query="测试查询", top_k=20
            )

        # 成功 KB 结果正常返回，失败 KB 不影响
        assert [h["term_id"] for h in result] == ["tid_ok"]
        # 两个 KB 都被尝试（并发发起）
        assert set(attempted) == {"kb_1", "kb_2"}
        # 失败仅告警不中断
        fail_warnings = [
            str(c)
            for c in mock_logger.warning.call_args_list
            if "chunk search failed" in str(c)
        ]
        assert len(fail_warnings) == 1
        assert "kb_1" in fail_warnings[0]

    @pytest.mark.asyncio
    async def test_kb_searches_run_concurrently(self) -> None:
        """两个 KB 搜索并发执行；串行实现会因握手超时而失败。"""
        adapter = self._make_adapter()
        started = {kid: asyncio.Event() for kid in ("kb_1", "kb_2")}
        all_started = asyncio.Event()

        async def fake_chunk_search(
            *,
            kb_resource_id: str | None,
            **_: Any,
        ) -> list[dict[str, Any]]:
            kid = kb_resource_id or ""
            started[kid].set()
            if all(e.is_set() for e in started.values()):
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=2.0)
            return [{"term_id": f"tid_{kid}", "score": 0.9}]

        adapter._do_chunk_search = fake_chunk_search  # type: ignore[method-assign]

        result = await adapter._do_path2(self._kb_info(), query="测试查询", top_k=20)

        assert [h["term_id"] for h in result] == ["tid_kb_1", "tid_kb_2"]

    @pytest.mark.asyncio
    async def test_merge_order_follows_kb_info_iteration(self) -> None:
        """合并顺序与 kb_info 迭代顺序一致，与完成先后无关。"""
        adapter = self._make_adapter()

        async def fake_chunk_search(
            *,
            kb_resource_id: str | None,
            **_: Any,
        ) -> list[dict[str, Any]]:
            kid = kb_resource_id or ""
            # kb_1 最慢返回：若按完成顺序合并会排到末尾
            if kid == "kb_1":
                await asyncio.sleep(0.05)
            return [
                {"term_id": f"tid_{kid}_a", "score": 0.9},
                {"term_id": f"tid_{kid}_b", "score": 0.8},
            ]

        adapter._do_chunk_search = fake_chunk_search  # type: ignore[method-assign]

        result = await adapter._do_path2(self._kb_info(), query="测试查询", top_k=20)

        assert [h["term_id"] for h in result] == [
            "tid_kb_1_a",
            "tid_kb_1_b",
            "tid_kb_2_a",
            "tid_kb_2_b",
        ]

    @pytest.mark.asyncio
    async def test_cross_kb_dedup_keeps_first_term_id(self) -> None:
        """跨 KB 相同 term_id 只保留首个（按 kb_info 迭代顺序）。"""
        adapter = self._make_adapter()

        async def fake_chunk_search(
            *,
            kb_resource_id: str | None,
            **_: Any,
        ) -> list[dict[str, Any]]:
            kid = kb_resource_id or ""
            if kid == "kb_1":
                return [
                    {"term_id": "shared", "score": 0.9},
                    {"term_id": "only_kb_1", "score": 0.8},
                ]
            return [
                {"term_id": "shared", "score": 0.7},
                {"term_id": "only_kb_2", "score": 0.6},
            ]

        adapter._do_chunk_search = fake_chunk_search  # type: ignore[method-assign]

        result = await adapter._do_path2(self._kb_info(), query="测试查询", top_k=20)

        assert [h["term_id"] for h in result] == [
            "shared",
            "only_kb_1",
            "only_kb_2",
        ]

    @pytest.mark.asyncio
    async def test_empty_kb_info_returns_empty(self) -> None:
        """空 kb_info 直接返回空列表，不发起任何搜索。"""
        adapter = self._make_adapter()

        async def fake_chunk_search(
            *,
            kb_resource_id: str | None,
            **_: Any,
        ) -> list[dict[str, Any]]:
            raise AssertionError("不应发起搜索")

        adapter._do_chunk_search = fake_chunk_search  # type: ignore[method-assign]

        assert await adapter._do_path2({}, query="测试查询", top_k=20) == []
