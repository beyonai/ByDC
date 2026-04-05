"""
Agent 创建测试（Deep Agents 架构）
"""

import pytest
from unittest.mock import Mock, patch
from datacloud_analysis.agent import create_agent


class TestAgentCreation:
    """测试 Agent 创建"""

    def test_create_agent_calls_deep_agent(self):
        """测试 create_agent 调用 Deep Agents SDK"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_agent = Mock()
            mock_deep.return_value = mock_agent

            agent = create_agent(locale="zh_CN")

            mock_deep.assert_called_once()
            assert agent == mock_agent

    def test_create_agent_with_custom_locale(self):
        """测试自定义 locale"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_agent = Mock()
            mock_deep.return_value = mock_agent

            agent = create_agent(locale="en_US")

            mock_deep.assert_called_once()
            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["locale"] == "en_US"

    def test_create_agent_with_unsupported_locale_falls_back_to_zh_CN(self):
        """测试不支持的 locale 回退到 zh_CN"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_agent = Mock()
            mock_deep.return_value = mock_agent

            agent = create_agent(locale="invalid_locale")

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["locale"] == "zh_CN"

    def test_create_agent_with_tools(self):
        """测试注入自定义工具"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_agent = Mock()
            mock_deep.return_value = mock_agent

            custom_tools = {"custom_tool": Mock()}
            agent = create_agent(tools=custom_tools)

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["tools"] == custom_tools

    def test_create_agent_passes_model_params(self):
        """测试模型参数正确传递"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            create_agent(model="claude-opus-4-6", api_key="test-key", base_url="http://test")

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["model"] == "claude-opus-4-6"
            assert call_kwargs["api_key"] == "test-key"
            assert call_kwargs["base_url"] == "http://test"
