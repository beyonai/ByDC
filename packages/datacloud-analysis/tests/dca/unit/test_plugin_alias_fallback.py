"""Tests for Layer 3: plugin fast path + catalog fallback."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

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

    def test_returns_empty_when_sdk_unavailable(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        with patch(f"{_PLUGIN_MOD}._HAS_RESOLVE_ALIASES", False):
            resolved, unresolved = _resolve_via_aliases(["营收"], [], "scope")
        assert resolved == {}
        assert unresolved == ["营收"]

    def test_returns_empty_on_empty_terms(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        resolved, unresolved = _resolve_via_aliases([], [], "scope")
        assert resolved == {}
        assert unresolved == []

    def test_returns_empty_on_empty_scope(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        resolved, unresolved = _resolve_via_aliases(["营收"], [], "")
        assert resolved == {}
        assert unresolved == ["营收"]

    def test_returns_resolved_and_unresolved(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )
        from datacloud_knowledge.search.types import FieldResolutionResult

        mock_result = FieldResolutionResult(
            resolved={"营收": "total_revenue"},
            ambiguous={},
            unresolved=["不存在"],
        )
        with patch(f"{_PLUGIN_MOD}.resolve_field_aliases", return_value=mock_result):
            resolved, unresolved = _resolve_via_aliases(
                ["营收", "不存在"], [], "scene_enterprise_analysis"
            )
        assert resolved == {"营收": "total_revenue"}
        assert unresolved == ["不存在"]

    def test_ambiguous_merged_into_unresolved(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )
        from datacloud_knowledge.search.types import (
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
            resolved, unresolved = _resolve_via_aliases(["营收"], [], "scene_enterprise_analysis")
        assert resolved == {}
        assert unresolved == ["营收"]

    def test_exception_returns_fallback(self) -> None:
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            _resolve_via_aliases,
        )

        with patch(
            f"{_PLUGIN_MOD}.resolve_field_aliases",
            side_effect=RuntimeError("DB down"),
        ):
            resolved, unresolved = _resolve_via_aliases(["营收"], [], "scene_enterprise_analysis")
        assert resolved == {}
        assert unresolved == ["营收"]


@pytest.mark.intent
class TestMainFlowFallback:
    """Main flow: alias fast path → catalog fallback for unresolved."""

    @pytest.mark.asyncio
    async def test_alias_resolves_all_no_catalog_needed(self) -> None:
        """All terms resolved by alias → no slow path triggered."""
        from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
            before_call_back,
        )

        ctx = _make_ctx()

        with patch(
            f"{_PLUGIN_MOD}._resolve_via_aliases",
            return_value=({"营收": "total_revenue"}, []),
        ):
            result = await before_call_back(ctx)

        # No ClarificationNeededError → all resolved, simple query returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_alias_partial_unresolved_triggers_confirm(self) -> None:
        """Alias resolves some, unresolved remain → NEED_CONFIRM path.

        interrupt is None in test env → skip clarification, return None.
        """
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
            patch(f"{_PLUGIN_MOD}.interrupt", None),
        ):
            result = await before_call_back(ctx)

        assert result is None
