"""TC-A / TC-B：OntologyToolLoader.build_nl_query_tool + configure_loader 验收。

TC-A：build_nl_query_tool
  TC-A1  build_nl_query_tool 仅对 OBJECT 类型对象生成工具
  TC-A2  生成的工具 name 以 "nl_query_" 开头
  TC-A3  生成的工具 description 含 obj.name
  TC-A4  参数通过 object.query() 执行
  TC-A5  传入 knowledge_context 时透传
  TC-A6  传入 None knowledge_context 时透传 None

（TC-B：configure_loader 已随函数删除而移除）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owl_object_action() -> dict:
    return {"name": "enterprise_query", "label": "企业查询", "description": "企业信息查询动作"}


@pytest.fixture
def owl_object() -> dict:
    return {"name": "企业信息", "actions": []}


# ---------------------------------------------------------------------------
# TC-A：build_nl_query_tool
# ---------------------------------------------------------------------------


class TestBuildNLQueryTool:
    # ------------------------------------------------------------------
    # TC-A1：仅对 OBJECT 类型对象生成工具
    # ------------------------------------------------------------------

    def test_TC_A1_only_object_types(self) -> None:
        """TC-A1：输入含 OBJECT / VIEW / ACTION 等多种类型时，仅 OBJECT 生成工具。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["obj_a", "obj_b"]
        loader.get_object.return_value = MagicMock()
        loader.get_object.return_value.name = "对象A"

        sut = OntologyToolLoader(mounted_objects=["obj_a", "obj_b"], loader=loader)
        result = sut.build_nl_query_tool()

        assert len(result) == 2
        for name in result:
            assert name.startswith("nl_query_")

    # ------------------------------------------------------------------
    # TC-A2：生成的工具 name 以 "nl_query_" 开头
    # ------------------------------------------------------------------

    def test_TC_A2_tool_name_prefix(self) -> None:
        """TC-A2：生成的工具 name 以 "nl_query_" 开头。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["enterprise"]
        loader.get_object.return_value = MagicMock()
        loader.get_object.return_value.name = "企业信息"

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        result = sut.build_nl_query_tool()

        assert "nl_query_enterprise" in result

    # ------------------------------------------------------------------
    # TC-A3：生成的工具 description 含 obj.name
    # ------------------------------------------------------------------

    def test_TC_A3_description_includes_obj_name(self) -> None:
        """TC-A3：生成的工具 description 含 obj.name。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["enterprise"]
        obj = MagicMock()
        obj.name = "企业信息"
        loader.get_object.return_value = obj

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        result = sut.build_nl_query_tool()

        tool = result["nl_query_enterprise"]
        assert "企业信息" in tool.description

    # ------------------------------------------------------------------
    # TC-A4：参数通过 object.query() 执行
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_TC_A4_calls_object_query(self) -> None:
        """TC-A4：工具执行时调用 object.query(question=..., knowledge_context=...)。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["enterprise"]
        obj = MagicMock()
        obj.name = "企业信息"
        obj.query = MagicMock()
        obj.query.return_value = {"result": "ok"}
        loader.get_object.return_value = obj

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        result = sut.build_nl_query_tool()

        tool = result["nl_query_enterprise"]
        assert tool.coroutine is not None
        await tool.coroutine(question="test question")

        obj.query.assert_called_once()
        call_kwargs = obj.query.call_args.kwargs
        assert call_kwargs.get("question") == "test question"

    # ------------------------------------------------------------------
    # TC-A5：传入 knowledge_context 时透传
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_TC_A5_passes_knowledge_context(self) -> None:
        """TC-A5：传入 knowledge_context 时透传给 object.query()。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["enterprise"]
        obj = MagicMock()
        obj.name = "企业信息"
        obj.query = MagicMock()
        obj.query.return_value = {"result": "ok"}
        loader.get_object.return_value = obj

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        result = sut.build_nl_query_tool()

        tool = result["nl_query_enterprise"]
        await tool.coroutine(question="test", knowledge_context={"ctx": "data"})

        call_kwargs = obj.query.call_args.kwargs
        assert call_kwargs.get("knowledge_context") == {"ctx": "data"}

    # ------------------------------------------------------------------
    # TC-A6：传入 None knowledge_context 时透传 None
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_TC_A6_passes_none_knowledge_context(self) -> None:
        """TC-A6：传入 None knowledge_context 时透传 None。"""
        from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

        loader = MagicMock(spec=OntologyLoader)
        loader.list_objects.return_value = ["enterprise"]
        obj = MagicMock()
        obj.name = "企业信息"
        obj.query = MagicMock()
        obj.query.return_value = {"result": "ok"}
        loader.get_object.return_value = obj

        sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=loader)
        result = sut.build_nl_query_tool()

        tool = result["nl_query_enterprise"]
        await tool.coroutine(question="test")

        loader.get_object.return_value.query.assert_called_once_with(
            question="test",
            knowledge_context=None,
        )
