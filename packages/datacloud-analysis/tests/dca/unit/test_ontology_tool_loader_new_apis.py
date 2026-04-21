"""TC-A / TC-B：OntologyToolLoader.build_nl_query_tool + configure_loader 验收。

覆盖：
  TC-A1  build_nl_query_tool OBJECT → StructuredTool 名称为 data_query_{code}
  TC-A2  build_nl_query_tool VIEW   → StructuredTool 名称为 data_query_{code}
  TC-A3  inject_context_knowledge=True  → schema 含 contextKnowledge 字段
  TC-A4  inject_context_knowledge=False → schema 不含 contextKnowledge 字段
  TC-A5  OBJECT 执行路径：调用 loader.get_object(code).query(question=..., knowledge_context=...)
  TC-A6  VIEW 执行路径：调用 loader.get_view(code).query(question=..., knowledge_context=...)
  TC-A7  contextKnowledge="" 时 knowledge_context 传 None（空串转 None）
  TC-B1  configure_loader 调用 loader.configure(plan_generator=..., term_loader=..., ...)
  TC-B2  configure_loader 以正确参数构造 LangGraphPlanGenerator
  TC-B3  configure_loader 可从 datacloud_analysis.tools.ontology_tool_loader 直接导入
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest


# ---------------------------------------------------------------------------
# 共用 helpers
# ---------------------------------------------------------------------------


def _make_loader(biz_type: str = "OBJECT") -> Any:
    loader = Mock()
    mock_obj = Mock()
    mock_obj.query = AsyncMock(return_value={"rows": []})
    mock_view = Mock()
    mock_view.query = AsyncMock(return_value={"rows": []})

    if biz_type == "VIEW":
        loader.get_object.side_effect = KeyError("not an object")
        loader.get_view.return_value = mock_view
    else:
        loader.get_ontology_class.return_value = mock_obj
        loader.get_object.return_value = mock_obj
        loader.get_view.side_effect = KeyError("not a view")

    loader._scenes = {"scene_view": Mock()} if biz_type == "VIEW" else {}
    return loader


# ---------------------------------------------------------------------------
# TC-A：build_nl_query_tool
# ---------------------------------------------------------------------------


class TestBuildNlQueryTool:
    def _make_sut(self, biz_type: str = "OBJECT") -> Any:
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        return OntologyToolLoader(
            mounted_objects=["enterprise"],
            loader=_make_loader(biz_type),
        )

    # ------------------------------------------------------------------
    # TC-A1 / TC-A2：工具名称
    # ------------------------------------------------------------------

    def test_TC_A1_object_tool_name(self) -> None:
        """TC-A1：OBJECT 类型生成工具名为 data_query_{code}。"""
        sut = self._make_sut("OBJECT")
        tool = sut.build_nl_query_tool(
            resource_code="enterprise",
            resource_biz_type="OBJECT",
            resource_name="企业分析",
            resource_desc="企业综合分析",
        )
        assert tool.name == "data_query_enterprise"

    def test_TC_A2_view_tool_name(self) -> None:
        """TC-A2：VIEW 类型生成工具名为 data_query_{code}。"""
        sut = self._make_sut("VIEW")
        tool = sut.build_nl_query_tool(
            resource_code="scene_enterprise",
            resource_biz_type="VIEW",
            resource_name="企业综合分析视图",
            resource_desc="",
        )
        assert tool.name == "data_query_scene_enterprise"

    # ------------------------------------------------------------------
    # TC-A3 / TC-A4：contextKnowledge 字段控制
    # ------------------------------------------------------------------

    def test_TC_A3_inject_context_knowledge_true_has_field(self) -> None:
        """TC-A3：inject_context_knowledge=True（默认）时 schema 含 contextKnowledge。"""
        sut = self._make_sut()
        tool = sut.build_nl_query_tool(
            resource_code="enterprise",
            resource_biz_type="OBJECT",
            resource_name="企业分析",
            resource_desc="",
            inject_context_knowledge=True,
        )
        schema = tool.args_schema.model_json_schema()
        assert "contextKnowledge" in schema.get("properties", {}), (
            "inject_context_knowledge=True 时 schema 应含 contextKnowledge"
        )

    def test_TC_A4_inject_context_knowledge_false_no_field(self) -> None:
        """TC-A4：inject_context_knowledge=False 时 schema 不含 contextKnowledge。"""
        sut = self._make_sut()
        tool = sut.build_nl_query_tool(
            resource_code="enterprise",
            resource_biz_type="OBJECT",
            resource_name="企业分析",
            resource_desc="",
            inject_context_knowledge=False,
        )
        schema = tool.args_schema.model_json_schema()
        assert "contextKnowledge" not in schema.get("properties", {}), (
            "inject_context_knowledge=False 时 schema 不应含 contextKnowledge"
        )

    # ------------------------------------------------------------------
    # TC-A5 / TC-A6：执行路径
    # ------------------------------------------------------------------

    def test_TC_A5_object_execute_calls_get_object_query(self) -> None:
        """TC-A5：OBJECT 执行时调用 loader.get_object(code).query(question=..., knowledge_context=...)。"""
        loader = _make_loader("OBJECT")
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        tool = sut.build_nl_query_tool(
            resource_code="enterprise",
            resource_biz_type="OBJECT",
            resource_name="企业分析",
            resource_desc="",
        )

        asyncio.get_event_loop().run_until_complete(
            tool.coroutine(query="查询所有企业", contextKnowledge="some context")
        )

        loader.get_object.assert_called_once_with("enterprise")
        loader.get_object.return_value.query.assert_called_once_with(
            question="查询所有企业",
            knowledge_context="some context",
        )

    def test_TC_A6_view_execute_calls_get_view_query(self) -> None:
        """TC-A6：VIEW 执行时调用 loader.get_view(code).query(question=..., knowledge_context=...)。"""
        loader = _make_loader("VIEW")
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        sut = OntologyToolLoader(mounted_objects=["scene_enterprise"], loader=loader)
        tool = sut.build_nl_query_tool(
            resource_code="scene_enterprise",
            resource_biz_type="VIEW",
            resource_name="企业视图",
            resource_desc="",
        )

        asyncio.get_event_loop().run_until_complete(
            tool.coroutine(query="查询企业列表", contextKnowledge="")
        )

        loader.get_view.assert_called_once_with("scene_enterprise")
        loader.get_view.return_value.query.assert_called_once_with(
            question="查询企业列表",
            knowledge_context=None,  # 空串应转 None
        )

    # ------------------------------------------------------------------
    # TC-A7：空串 contextKnowledge 转 None
    # ------------------------------------------------------------------

    def test_TC_A7_empty_context_knowledge_becomes_none(self) -> None:
        """TC-A7：contextKnowledge="" 时传入 query() 的 knowledge_context 应为 None。"""
        loader = _make_loader("OBJECT")
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        tool = sut.build_nl_query_tool(
            resource_code="enterprise",
            resource_biz_type="OBJECT",
            resource_name="企业分析",
            resource_desc="",
        )

        asyncio.get_event_loop().run_until_complete(
            tool.coroutine(query="test", contextKnowledge="")
        )

        loader.get_object.return_value.query.assert_called_once_with(
            question="test",
            knowledge_context=None,
        )


# ---------------------------------------------------------------------------
# TC-B：configure_loader
# ---------------------------------------------------------------------------


class TestConfigureLoader:
    # ------------------------------------------------------------------
    # TC-B3：可导入
    # ------------------------------------------------------------------

    def test_TC_B3_importable_from_module(self) -> None:
        """TC-B3：configure_loader 可从 datacloud_analysis.tools.ontology_tool_loader 导入。"""
        from datacloud_analysis.tools.ontology_tool_loader import configure_loader  # noqa: F401

    # ------------------------------------------------------------------
    # TC-B1：调用 loader.configure
    # ------------------------------------------------------------------

    def test_TC_B1_calls_loader_configure(self) -> None:
        """TC-B1：configure_loader 调用 loader.configure 且包含 plan_generator / term_loader / csv_base_dir。"""
        from datacloud_analysis.tools.ontology_tool_loader import configure_loader

        loader = Mock()

        with (
            patch(
                "datacloud_analysis.tools.ontology_tool_loader.LangGraphPlanGenerator",
                autospec=False,
            ) as mock_pg_cls,
            patch(
                "datacloud_analysis.tools.ontology_tool_loader.TermLoader",
                autospec=False,
            ) as mock_tl_cls,
        ):
            mock_pg_cls.return_value = MagicMock(name="pg_instance")
            mock_tl_cls.from_config.return_value = MagicMock(name="tl_instance")

            configure_loader(
                loader,
                model="gpt-4o",
                base_url="https://api.example.com",
                api_key="sk-test",
                csv_base_dir="/tmp/workspace",
                sql_execution_mode="internal",
            )

        loader.configure.assert_called_once()
        kwargs = loader.configure.call_args.kwargs
        assert "plan_generator" in kwargs
        assert "term_loader" in kwargs
        assert kwargs.get("csv_base_dir") == "/tmp/workspace"
        assert kwargs.get("sql_execution_mode") == "internal"

    # ------------------------------------------------------------------
    # TC-B2：LangGraphPlanGenerator 构造参数
    # ------------------------------------------------------------------

    def test_TC_B2_plan_generator_constructed_with_correct_args(self) -> None:
        """TC-B2：LangGraphPlanGenerator 以 model / base_url / api_key / temperature 构造。"""
        from datacloud_analysis.tools.ontology_tool_loader import configure_loader

        loader = Mock()

        with (
            patch(
                "datacloud_analysis.tools.ontology_tool_loader.LangGraphPlanGenerator",
            ) as mock_pg_cls,
            patch(
                "datacloud_analysis.tools.ontology_tool_loader.TermLoader",
            ) as mock_tl_cls,
        ):
            mock_tl_cls.from_config.return_value = MagicMock()

            configure_loader(
                loader,
                model="Qwen/Qwen3-235B-A22B",
                base_url="https://qwen.api/v1",
                api_key="sk-qwen",
                temperature=0.0,
                csv_base_dir="/tmp/dc",
            )

        mock_pg_cls.assert_called_once()
        pg_kwargs = mock_pg_cls.call_args.kwargs
        assert pg_kwargs.get("model") == "Qwen/Qwen3-235B-A22B"
        assert pg_kwargs.get("base_url") == "https://qwen.api/v1"
        assert pg_kwargs.get("api_key") == "sk-qwen"
        assert pg_kwargs.get("temperature") == 0.0
