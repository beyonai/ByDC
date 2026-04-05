"""
测试 Deep Agents 集成
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDeepAgentsIntegration:
    """测试 Deep Agents SDK 集成"""

    def test_create_agent_uses_deep_agents(self):
        """测试使用 Deep Agents SDK 创建 agent"""
        mock_agent = Mock()
        mock_agent.compile.return_value = mock_agent

        # Patch the internal _create_deep_agent function
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_internal:
            mock_internal.return_value = mock_agent

            from datacloud_analysis.agent import create_agent

            agent = create_agent(locale="zh_CN")

            # 验证调用了内部函数
            mock_internal.assert_called_once()
            assert agent == mock_agent

    def test_deep_agents_with_real_sdk(self):
        """测试使用真实的 Deep Agents SDK（如果可用）"""
        try:
            from deepagents import create_deep_agent
            from datacloud_analysis.agent import create_agent

            # 只测试能否成功调用，不验证结果（需要 API key）
            # 这个测试会在 deepagents 可用时运行
            assert callable(create_agent)
        except ImportError:
            pytest.skip("deepagents not installed")


class TestDeepAgentsRealImport:
    """测试真实的 deepagents 导入"""

    def test_deepagents_import(self):
        """测试 deepagents 可以导入"""
        try:
            from deepagents import create_deep_agent
            assert callable(create_deep_agent)
        except ImportError:
            pytest.skip("deepagents not installed")

    def test_agent_creation_real(self):
        """测试真实创建 agent（不执行）"""
        try:
            from datacloud_analysis.agent import _create_deep_agent
            # 只测试函数存在，不实际创建 agent（需要 API key）
            assert callable(_create_deep_agent)
        except ImportError:
            pytest.skip("deepagents not installed")

    def test_create_agent_with_deepagents_installed(self):
        """测试在 deepagents 已安装时创建 agent"""
        try:
            from deepagents import create_deep_agent
            from datacloud_analysis.agent import create_agent
            from datacloud_analysis.tools.registry import register_all_tools

            # 验证工具注册正常
            tools = register_all_tools()
            assert len(tools) > 0

            # 验证 create_agent 函数可调用
            assert callable(create_agent)

        except ImportError:
            pytest.skip("deepagents not installed")
