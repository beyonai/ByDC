"""Tests for scope-aware recall clause generation."""

from __future__ import annotations

import json

import pytest


def _get_batch_module():  # type: ignore[no-untyped-def]
    from datacloud_knowledge.intent import batch_recall

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
