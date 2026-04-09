"""
阶段1：system_prompt 修复测试

测试 task_prompt 追加到 system_prompt 的逻辑
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datacloud_analysis.agent import _create_deep_agent


class TestSystemPromptStage1:
    """测试阶段1的 system_prompt 和 task_prompt 处理"""

    @patch("datacloud_analysis.agent.pathlib")
    @patch("datacloud_analysis.session.checkpointer.get_checkpointer")
    @patch("deepagents.create_deep_agent")
    @patch("datacloud_analysis.backend.create_datacloud_backend")
    @patch("datacloud_analysis.tools.registry.register_all_tools")
    def test_task_prompt_appended_to_system_prompt(
        self,
        mock_register_tools,
        mock_backend,
        mock_create_deep_agent,
        mock_checkpointer,
        mock_pathlib,
    ):
        """测试 task_prompt 正确追加到 system_prompt"""
        # Setup mocks
        mock_register_tools.return_value = []
        mock_backend.return_value = Mock()
        mock_checkpointer.return_value = Mock()
        mock_agent = Mock()
        mock_create_deep_agent.return_value = mock_agent

        # Mock pathlib.Path
        mock_path = Mock()
        mock_path.parent = Mock()
        mock_path.parent.__truediv__ = Mock(return_value=Mock())
        mock_pathlib.Path.return_value = mock_path

        custom_system = "你是数字员工"
        task_prompt_content = "请遵循以下原则：\n1. 单一技能优先"

        # 调用 _create_deep_agent
        result = _create_deep_agent(
            system_prompt=custom_system, task_prompt=task_prompt_content, locale="zh_CN"
        )

        # 验证 create_deep_agent 被调用
        mock_create_deep_agent.assert_called_once()

        # 验证 system_prompt 参数
        call_kwargs = mock_create_deep_agent.call_args[1]
        final_prompt = call_kwargs["system_prompt"]

        # 验证包含原始 system_prompt
        assert custom_system in final_prompt
        # 验证包含 task_prompt 标题
        assert "# 任务处理指导" in final_prompt
        # 验证包含 task_prompt 内容
        assert task_prompt_content in final_prompt
        # 验证顺序：system_prompt 在前，task_prompt 在后
        assert final_prompt.index(custom_system) < final_prompt.index("# 任务处理指导")
        assert final_prompt.index("# 任务处理指导") < final_prompt.index(task_prompt_content)

    @patch("datacloud_analysis.agent.pathlib")
    @patch("datacloud_analysis.session.checkpointer.get_checkpointer")
    @patch("deepagents.create_deep_agent")
    @patch("datacloud_analysis.backend.create_datacloud_backend")
    @patch("datacloud_analysis.tools.registry.register_all_tools")
    def test_system_prompt_without_task_prompt(
        self,
        mock_register_tools,
        mock_backend,
        mock_create_deep_agent,
        mock_checkpointer,
        mock_pathlib,
    ):
        """测试没有 task_prompt 时，只使用 system_prompt"""
        # Setup mocks
        mock_register_tools.return_value = []
        mock_backend.return_value = Mock()
        mock_checkpointer.return_value = Mock()
        mock_agent = Mock()
        mock_create_deep_agent.return_value = mock_agent

        # Mock pathlib.Path
        mock_path = Mock()
        mock_path.parent = Mock()
        mock_path.parent.__truediv__ = Mock(return_value=Mock())
        mock_pathlib.Path.return_value = mock_path

        custom_system = "你是数字员工"

        # 调用 _create_deep_agent，不传 task_prompt
        result = _create_deep_agent(system_prompt=custom_system, task_prompt=None, locale="zh_CN")

        # 验证 system_prompt 参数
        call_kwargs = mock_create_deep_agent.call_args[1]
        final_prompt = call_kwargs["system_prompt"]

        # 验证只包含 system_prompt，没有追加 task_prompt
        assert final_prompt == custom_system
        assert "# 任务处理指导" not in final_prompt

    @patch("datacloud_analysis.agent.pathlib")
    @patch("datacloud_analysis.session.checkpointer.get_checkpointer")
    @patch("deepagents.create_deep_agent")
    @patch("datacloud_analysis.backend.create_datacloud_backend")
    @patch("datacloud_analysis.tools.registry.register_all_tools")
    def test_default_system_prompt_when_none(
        self,
        mock_register_tools,
        mock_backend,
        mock_create_deep_agent,
        mock_checkpointer,
        mock_pathlib,
    ):
        """测试当 system_prompt=None 时，使用默认 prompt"""
        # Setup mocks
        mock_register_tools.return_value = []
        mock_backend.return_value = Mock()
        mock_checkpointer.return_value = Mock()
        mock_agent = Mock()
        mock_create_deep_agent.return_value = mock_agent

        # Mock pathlib.Path
        mock_path = Mock()
        mock_path.parent = Mock()
        mock_path.parent.__truediv__ = Mock(return_value=Mock())
        mock_pathlib.Path.return_value = mock_path

        # 调用 _create_deep_agent，不传 system_prompt
        result = _create_deep_agent(system_prompt=None, task_prompt=None, locale="zh_CN")

        # 验证使用了默认 prompt
        call_kwargs = mock_create_deep_agent.call_args[1]
        final_prompt = call_kwargs["system_prompt"]

        # 验证包含默认 prompt 的关键内容
        assert "DataCloud Agent" in final_prompt
        assert "数据分析助手" in final_prompt
        assert "query_objects" in final_prompt

    @patch("datacloud_analysis.agent.pathlib")
    @patch("datacloud_analysis.session.checkpointer.get_checkpointer")
    @patch("deepagents.create_deep_agent")
    @patch("datacloud_analysis.backend.create_datacloud_backend")
    @patch("datacloud_analysis.tools.registry.register_all_tools")
    def test_default_prompt_with_task_prompt(
        self,
        mock_register_tools,
        mock_backend,
        mock_create_deep_agent,
        mock_checkpointer,
        mock_pathlib,
    ):
        """测试默认 prompt + task_prompt 的组合"""
        # Setup mocks
        mock_register_tools.return_value = []
        mock_backend.return_value = Mock()
        mock_checkpointer.return_value = Mock()
        mock_agent = Mock()
        mock_create_deep_agent.return_value = mock_agent

        # Mock pathlib.Path
        mock_path = Mock()
        mock_path.parent = Mock()
        mock_path.parent.__truediv__ = Mock(return_value=Mock())
        mock_pathlib.Path.return_value = mock_path

        task_prompt_content = "请优先使用单一技能"

        # 调用 _create_deep_agent
        result = _create_deep_agent(
            system_prompt=None,  # 使用默认
            task_prompt=task_prompt_content,
            locale="zh_CN",
        )

        # 验证
        call_kwargs = mock_create_deep_agent.call_args[1]
        final_prompt = call_kwargs["system_prompt"]

        # 验证包含默认 prompt 和 task_prompt
        assert "DataCloud Agent" in final_prompt
        assert "# 任务处理指导" in final_prompt
        assert task_prompt_content in final_prompt
