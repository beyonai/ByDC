"""
Agent 创建测试
"""

import pytest
from unittest.mock import Mock, patch
from datacloud_analysis.agent import create_agent


class TestAgentCreation:
    """测试 Agent 创建"""

    def test_create_agent_with_legacy_fallback(self):
        """测试使用 legacy StateGraph 创建 agent"""
        # Mock _create_deep_agent to raise ImportError, forcing fallback
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.agent._create_legacy_agent") as mock_legacy:
                mock_agent = Mock()
                mock_legacy.return_value = mock_agent

                agent = create_agent(locale="zh_CN")

                # 验证使用了 legacy 实现
                mock_legacy.assert_called_once()
                assert agent == mock_agent

    def test_create_agent_with_custom_locale(self):
        """测试自定义 locale"""
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.agent._create_legacy_agent") as mock_legacy:
                mock_agent = Mock()
                mock_legacy.return_value = mock_agent

                agent = create_agent(locale="en_US")

                mock_legacy.assert_called_once()

    def test_create_agent_with_unsupported_locale(self):
        """测试不支持的 locale 回退到 zh_CN"""
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.agent._create_legacy_agent") as mock_legacy:
                mock_agent = Mock()
                mock_legacy.return_value = mock_agent

                agent = create_agent(locale="invalid_locale")

                # 应该回退到 zh_CN
                mock_legacy.assert_called_once()
                # 验证传递的 locale 是 zh_CN
                call_kwargs = mock_legacy.call_args[1]
                assert call_kwargs["locale"] == "zh_CN"

    def test_create_agent_with_tools(self):
        """测试注入自定义工具"""
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.agent._create_legacy_agent") as mock_legacy:
                mock_agent = Mock()
                mock_legacy.return_value = mock_agent

                custom_tools = {"custom_tool": Mock()}
                agent = create_agent(tools=custom_tools)

                # 验证工具被传递
                call_kwargs = mock_legacy.call_args[1]
                assert call_kwargs["tools"] == custom_tools

    def test_create_agent_with_checkpointer(self):
        """测试使用 checkpointer"""
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.orchestration.graph_builder.build_analysis_graph") as mock_build, \
                 patch("datacloud_analysis.session.checkpointer.get_checkpointer") as mock_checkpointer:

                mock_graph = Mock()
                mock_compiled = Mock()
                mock_checkpointer_instance = Mock()

                mock_graph.compile.return_value = mock_compiled
                mock_build.return_value = mock_graph
                mock_checkpointer.return_value = mock_checkpointer_instance

                agent = create_agent()

                # 验证使用了 checkpointer
                mock_graph.compile.assert_called_once_with(checkpointer=mock_checkpointer_instance)

    def test_create_agent_without_checkpointer(self):
        """测试没有 checkpointer 的情况"""
        with patch("datacloud_analysis.agent._create_deep_agent", side_effect=ImportError):
            with patch("datacloud_analysis.orchestration.graph_builder.build_analysis_graph") as mock_build, \
                 patch("datacloud_analysis.session.checkpointer.get_checkpointer", side_effect=RuntimeError):

                mock_graph = Mock()
                mock_compiled = Mock()
                mock_graph.compile.return_value = mock_compiled
                mock_build.return_value = mock_graph

                agent = create_agent()

                # 验证没有使用 checkpointer
                mock_graph.compile.assert_called_once_with()
