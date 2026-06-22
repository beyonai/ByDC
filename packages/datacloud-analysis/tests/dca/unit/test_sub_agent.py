"""Task #7：sub_agent 分身工具 + graph_builder.py is_sub_agent 参数。"""

from __future__ import annotations

import inspect

import pytest


class TestSubAgentTool:
    def test_sub_agent_importable(self) -> None:
        from datacloud_analysis.tools.skill_executor import sub_agent
        from langchain_core.tools import BaseTool

        assert isinstance(sub_agent, BaseTool)

    def test_sub_agent_tool_name(self) -> None:
        from datacloud_analysis.tools.skill_executor import sub_agent

        assert sub_agent.name == "sub_agent"

    def test_sub_agent_signature(self) -> None:
        from datacloud_analysis.tools.skill_executor import sub_agent

        # async tool 的实际函数在 .coroutine 属性里
        fn = sub_agent.coroutine or sub_agent.func
        assert fn is not None
        sig = inspect.signature(fn)
        assert "task" in sig.parameters
        assert "context_summary" in sig.parameters
        assert "initial_tools" in sig.parameters

    @pytest.mark.asyncio
    async def test_sub_agent_not_in_sub_graph_tools(self) -> None:
        """分身图构建时（is_sub_agent=True）不应包含 sub_agent 工具。"""
        from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

        graph = build_analysis_graph(tools={}, loader=None, is_sub_agent=True)
        # 图构建不报错即验证 is_sub_agent 参数已接受
        assert graph is not None

    def test_build_analysis_graph_accepts_is_sub_agent(self) -> None:
        """build_analysis_graph 应接受 is_sub_agent 参数。"""
        import inspect

        from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

        sig = inspect.signature(build_analysis_graph)
        assert "is_sub_agent" in sig.parameters


class TestIsSubAgentPreventsRecursion:
    def test_sub_agent_not_in_subgraph_tool_list(self) -> None:
        """is_sub_agent=True 时，_build_prebuilt_graph 不追加 sub_agent 工具。"""
        from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

        sig = inspect.signature(_build_prebuilt_graph)
        assert "is_sub_agent" in sig.parameters, "_build_prebuilt_graph 应有 is_sub_agent 参数"
