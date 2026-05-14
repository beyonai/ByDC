"""Tests for scope-aware recall clause generation."""

from __future__ import annotations

import json

import pytest


def _get_batch_module():  # type: ignore[no-untyped-def]
    from datacloud_knowledge.retrieval import recall as batch_recall

    return batch_recall


@pytest.mark.intent
class TestBuildEffectiveScopeClause:
    """_build_effective_scope_clause: strict vs non-strict."""

    def test_empty_scope_returns_empty(self) -> None:
        mod = _get_batch_module()
        assert mod._build_effective_scope_clause(None) == ""
        assert mod._build_effective_scope_clause("") == ""

    def test_strict_excludes_legacy_empty_scope(self) -> None:
        clause = _get_batch_module()._build_effective_scope_clause(
            "scene_enterprise_analysis", strict=True
        )
        assert "view_scope" in clause
        assert "obj_scope" in clause
        assert '"scope":"global"' in clause
        assert "= '{}'::jsonb" not in clause

    def test_non_strict_includes_legacy_empty_scope(self) -> None:
        clause = _get_batch_module()._build_effective_scope_clause(
            "scene_enterprise_analysis", strict=False
        )
        assert "view_scope" in clause
        assert "= '{}'::jsonb" in clause

    def test_default_is_non_strict(self) -> None:
        clause = _get_batch_module()._build_effective_scope_clause("scene_enterprise_analysis")
        assert "= '{}'::jsonb" in clause


@pytest.mark.intent
class TestBuildScopeParams:
    """_build_scope_params: correct JSON encoding."""

    def test_empty_scope_returns_empty_dict(self) -> None:
        assert _get_batch_module()._build_scope_params(None) == {}

    def test_scope_params_encode_correctly(self) -> None:
        params = _get_batch_module()._build_scope_params("scene_enterprise_analysis")
        assert json.loads(params["view_scope"]) == {
            "scope": "view",
            "code": "scene_enterprise_analysis",
        }
        assert json.loads(params["obj_scope"]) == {
            "scope": "object",
            "code": "scene_enterprise_analysis",
        }


@pytest.mark.intent
class TestRecallRequestIsValueRecall:
    """RecallRequest.is_value_recall correctly determines scope strictness."""

    def test_wherevalue_single_type_is_value_recall(self) -> None:
        """whereValue with 1 type_code should still be is_value_recall=True (non-strict)."""
        mod = _get_batch_module()
        req = mod.RecallRequest(
            map_key="k",
            keyword="test",
            ktype="whereValue",
            type_filter=frozenset({"enterprise_name"}),
            is_per_type=False,  # single type → not per_type
            per_type_limit=0,
            scope_code="scene_enterprise_analysis",
            is_value_recall=True,
        )
        # non-strict: allows legacy empty scope rows
        clause = mod._build_effective_scope_clause(req.scope_code, strict=not req.is_value_recall)
        assert "= '{}'::jsonb" in clause

    def test_select_ktype_is_not_value_recall(self) -> None:
        """select ktype should be strict (no legacy rows)."""
        mod = _get_batch_module()
        req = mod.RecallRequest(
            map_key="k",
            keyword="test",
            ktype="select",
            type_filter=frozenset({"prop"}),
            is_per_type=False,
            per_type_limit=0,
            scope_code="scene_enterprise_analysis",
            is_value_recall=False,
        )
        clause = mod._build_effective_scope_clause(req.scope_code, strict=not req.is_value_recall)
        assert "= '{}'::jsonb" not in clause


@pytest.mark.intent
class TestLayeredRecallFusion:
    """Layered recall helpers preserve ranking while bounding extra recall work."""

    def test_normalize_scope_layers_dedupes_and_caps(self) -> None:
        mod = _get_batch_module()

        layers = mod._normalize_scope_layers(
            [
                mod.ScopeRecallLayer(scope_code="view_a", weight=1.0),
                mod.ScopeRecallLayer(scope_code="object_a", weight=2.0),
                mod.ScopeRecallLayer(scope_code="object_a", weight=3.0),
                mod.ScopeRecallLayer(scope_code="object_b", weight=0.0),
                mod.ScopeRecallLayer(scope_code="object_c", weight=1.0),
                mod.ScopeRecallLayer(scope_code="object_d", weight=1.0),
                mod.ScopeRecallLayer(scope_code="object_e", weight=1.0),
            ]
        )

        assert [layer.scope_code for layer in layers] == [
            "view_a",
            "object_a",
            "object_c",
            "object_d",
        ]

    def test_weighted_fuse_candidate_layers_prefers_stronger_layer(self) -> None:
        mod = _get_batch_module()

        fused = mod._weighted_fuse_candidate_layers(
            [
                (
                    mod.ScopeRecallLayer(scope_code="view", weight=1.0),
                    [
                        {
                            "term_id": "manage_grid",
                            "term_name": "管理网格贡献率",
                            "term_type_code": "prop",
                            "name_id": "n1",
                            "term_code": "manage_grid_ratio",
                        }
                    ],
                ),
                (
                    mod.ScopeRecallLayer(scope_code="physical_grid", weight=2.0),
                    [
                        {
                            "term_id": "physical_grid",
                            "term_name": "物理网格贡献率",
                            "term_type_code": "prop",
                            "name_id": "n2",
                            "term_code": "physical_grid_ratio",
                        }
                    ],
                ),
            ],
            top_k=2,
            rrf_k=60,
        )

        assert [candidate["term_id"] for candidate in fused] == [
            "physical_grid",
            "manage_grid",
        ]
        assert fused[0]["match_type"] == "layered_multi_recall"

    def test_weighted_fuse_candidate_layers_retains_base_candidate(self) -> None:
        mod = _get_batch_module()

        fused = mod._weighted_fuse_candidate_layers(
            [
                (
                    mod.ScopeRecallLayer(scope_code="view", weight=1.0),
                    [
                        {
                            "term_id": "base_required",
                            "term_name": "原始贡献率候选",
                            "term_type_code": "prop",
                            "name_id": "n0",
                            "term_code": "base_required",
                        }
                    ],
                ),
                (
                    mod.ScopeRecallLayer(scope_code="object", weight=10.0),
                    [
                        {
                            "term_id": "object_a",
                            "term_name": "对象候选A",
                            "term_type_code": "prop",
                            "name_id": "n1",
                            "term_code": "object_a",
                        },
                        {
                            "term_id": "object_b",
                            "term_name": "对象候选B",
                            "term_type_code": "prop",
                            "name_id": "n2",
                            "term_code": "object_b",
                        },
                    ],
                ),
            ],
            top_k=2,
            rrf_k=60,
        )

        assert [candidate["term_id"] for candidate in fused] == ["object_a", "base_required"]
