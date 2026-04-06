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

    # ========== 阶段1：修复 system_prompt 测试 ==========

    def test_prompts_overwrite_system_prompt(self):
        """阶段1测试：prompts_overwrite 中的 system_prompt 能够覆盖默认 prompt"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            custom_system = "我是亦庄产业大脑数字员工"
            prompts_dict = {
                "system_prompt": custom_system
            }

            create_agent(prompts_overwrite=prompts_dict)

            call_kwargs = mock_deep.call_args[1]
            # 验证传递给 _create_deep_agent 的 system_prompt 是从 prompts_overwrite 来的
            assert call_kwargs["system_prompt"] == custom_system

    def test_prompts_overwrite_task_prompt(self):
        """阶段1测试：prompts_overwrite 中的 task_prompt 能够传递"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            task_prompt_content = "请根据以下原则来处理问题。\n# 单一技能优先原则：..."
            prompts_dict = {
                "task_prompt": task_prompt_content
            }

            create_agent(prompts_overwrite=prompts_dict)

            call_kwargs = mock_deep.call_args[1]
            # 验证 task_prompt 被传递
            assert call_kwargs["task_prompt"] == task_prompt_content

    def test_prompts_overwrite_both_prompts(self):
        """阶段1测试：同时设置 system_prompt 和 task_prompt"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            custom_system = "我是数字员工"
            task_prompt_content = "请遵循以下原则"
            prompts_dict = {
                "system_prompt": custom_system,
                "task_prompt": task_prompt_content
            }

            create_agent(prompts_overwrite=prompts_dict)

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["system_prompt"] == custom_system
            assert call_kwargs["task_prompt"] == task_prompt_content

    def test_prompts_overwrite_priority_over_system_prompt_param(self):
        """阶段1测试：prompts_overwrite 优先级高于 system_prompt 参数"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            direct_system = "直接传入的 system_prompt"
            overwrite_system = "prompts_overwrite 中的 system_prompt"

            prompts_dict = {
                "system_prompt": overwrite_system
            }

            create_agent(
                system_prompt=direct_system,
                prompts_overwrite=prompts_dict
            )

            call_kwargs = mock_deep.call_args[1]
            # 验证 prompts_overwrite 的优先级更高
            assert call_kwargs["system_prompt"] == overwrite_system

    def test_system_prompt_without_prompts_overwrite(self):
        """阶段1测试：没有 prompts_overwrite 时，使用直接传入的 system_prompt"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            direct_system = "直接传入的 system_prompt"

            create_agent(system_prompt=direct_system)

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["system_prompt"] == direct_system
            assert call_kwargs["task_prompt"] is None

