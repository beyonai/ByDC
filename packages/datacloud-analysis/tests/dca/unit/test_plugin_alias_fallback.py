"""Tests for Layer 3: plugin fast path + catalog fallback."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_PLUGIN_MOD = "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"


def _make_ctx(
    tool_name: str = "query_ads_enterprise_analysis",
    tool_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_params is None:
        tool_params = {
            "query": "查询营收",
            "select": [{"field_name_cn": "营收"}],
            "complex_conditions": [],
        }
    return {
        "tool_name": tool_name,
        "tool_params": tool_params,
        "graph_state": {},
    }


@pytest.mark.intent
class TestResolveViaAliases:
    """_resolve_via_aliases helper: SDK available / unavailable / exception."""

    def test_returns_none_when_sdk_unavailable(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        with patch(f"{_PLUGIN_MOD}._HAS_RESOLVE_ALIASES", False):
            result = _resolve_via_aliases(["营收"], "scene_enterprise_analysis")
        assert result is None

    def test_returns_none_on_empty_terms(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        result = _resolve_via_aliases([], "scene_enterprise_analysis")
        assert result is None

    def test_returns_none_on_empty_scope(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        result = _resolve_via_aliases(["营收"], "")
        assert result is None

    def test_returns_resolved_and_unresolved(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )
        from datacloud_knowledge.knowledge_search.types import FieldResolutionResult

        mock_result = FieldResolutionResult(
            resolved={"营收": "total_revenue"},
            ambiguous={},
            unresolved=["不存在"],
        )
        with patch(f"{_PLUGIN_MOD}.resolve_field_aliases", return_value=mock_result):
            result = _resolve_via_aliases(["营收", "不存在"], "scene_enterprise_analysis")
        assert result is not None
        resolved, unresolved = result
        assert resolved == {"营收": "total_revenue"}
        assert unresolved == ["不存在"]

    def test_ambiguous_merged_into_unresolved(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )
        from datacloud_knowledge.knowledge_search.types import (
            AmbiguousCandidate,
            FieldResolutionResult,
        )

        mock_result = FieldResolutionResult(
            resolved={},
            ambiguous={
                "营收": [
                    AmbiguousCandidate(
                        term_code="total_revenue",
                        term_name="总营收",
                        matched_alias="营收",
                        scope={"scope": "global"},
                    ),
                    AmbiguousCandidate(
                        term_code="net_revenue",
                        term_name="净营收",
                        matched_alias="营收",
                        scope={"scope": "global"},
                    ),
                ]
            },
            unresolved=[],
        )
        with patch(f"{_PLUGIN_MOD}.resolve_field_aliases", return_value=mock_result):
            result = _resolve_via_aliases(["营收"], "scene_enterprise_analysis")
        assert result is not None
        resolved, unresolved = result
        assert resolved == {}
        assert unresolved == ["营收"]

    def test_exception_returns_none(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        with patch(
            f"{_PLUGIN_MOD}.resolve_field_aliases",
            side_effect=RuntimeError("DB down"),
        ):
            result = _resolve_via_aliases(["营收"], "scene_enterprise_analysis")
        assert result is None


@pytest.mark.intent
class TestMainFlowFallback:
    """Main flow: alias fast path → catalog fallback for unresolved."""

    @pytest.mark.asyncio
    async def test_alias_resolves_all_no_catalog_needed(self) -> None:
        """All terms resolved by alias → catalog not called."""
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            before_call_back,
        )

        ctx = _make_ctx()
        catalog_mock = MagicMock(return_value={"total_revenue": "total_revenue"})

        with (
            patch(
                f"{_PLUGIN_MOD}._resolve_via_aliases",
                return_value=({"营收": "total_revenue"}, []),
            ),
            patch(f"{_PLUGIN_MOD}._get_field_catalog", catalog_mock),
        ):
            result = await before_call_back(ctx)  # noqa: F841

        catalog_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_alias_partial_catalog_fills_gap(self) -> None:
        """Alias resolves some, catalog resolves the rest → no SDK slow path."""
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            before_call_back,
        )

        ctx = _make_ctx(
            tool_params={
                "query": "查询营收和日期",
                "select": [
                    {"field_name_cn": "营收"},
                    {"field_name_cn": "日期"},
                ],
                "complex_conditions": [],
            }
        )

        with (
            patch(
                f"{_PLUGIN_MOD}._resolve_via_aliases",
                return_value=({"营收": "total_revenue"}, ["日期"]),
            ),
            patch(
                f"{_PLUGIN_MOD}._get_field_catalog",
                return_value={"日期": "stat_date"},
            ),
            patch(
                f"{_PLUGIN_MOD}._resolve_terms",
                return_value=({"日期": "stat_date"}, []),
            ),
        ):
            result = await before_call_back(ctx)  # noqa: F841

        # No ClarificationNeededError → all resolved
        # result is None or patch dict (no redirect since no complex_conditions)
