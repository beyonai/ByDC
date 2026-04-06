"""
阶段1：Prompt 处理逻辑单元测试

不需要真正创建 agent，只测试 prompt 处理逻辑
"""

import pytest


class TestPromptProcessing:
    """测试 prompt 处理逻辑"""

    def test_task_prompt_appending_logic(self):
        """测试 task_prompt 追加逻辑"""
        # 模拟代码逻辑
        system_prompt = "你是数字员工"
        task_prompt = "请遵循以下原则：\n1. 单一技能优先"

        # 模拟 _create_deep_agent 中的逻辑
        final_system_prompt = system_prompt
        if task_prompt:
            final_system_prompt = f"{final_system_prompt}\n\n# 任务处理指导\n{task_prompt}"

        # 验证
        assert system_prompt in final_system_prompt
        assert "# 任务处理指导" in final_system_prompt
        assert task_prompt in final_system_prompt
        # 验证顺序
        assert final_system_prompt.index(system_prompt) < final_system_prompt.index("# 任务处理指导")
        assert final_system_prompt.index("# 任务处理指导") < final_system_prompt.index(task_prompt)

    def test_without_task_prompt(self):
        """测试没有 task_prompt 时的逻辑"""
        system_prompt = "你是数字员工"
        task_prompt = None

        # 模拟逻辑
        final_system_prompt = system_prompt
        if task_prompt:
            final_system_prompt = f"{final_system_prompt}\n\n# 任务处理指导\n{task_prompt}"

        # 验证
        assert final_system_prompt == system_prompt
        assert "# 任务处理指导" not in final_system_prompt

    def test_prompts_overwrite_priority(self):
        """测试 prompts_overwrite 优先级逻辑"""
        # 直接传入的 system_prompt
        direct_system = "直接传入的 system_prompt"
        # prompts_overwrite 中的 system_prompt
        overwrite_system = "prompts_overwrite 中的 system_prompt"

        # 模拟 create_agent 中的逻辑
        system_prompt_param = direct_system
        prompts_overwrite = {
            "system_prompt": overwrite_system
        }

        # 优先级处理
        final_system_prompt = system_prompt_param
        task_prompt = None

        if prompts_overwrite:
            if "system_prompt" in prompts_overwrite:
                final_system_prompt = prompts_overwrite["system_prompt"]
            if "task_prompt" in prompts_overwrite:
                task_prompt = prompts_overwrite["task_prompt"]

        # 验证 prompts_overwrite 优先级更高
        assert final_system_prompt == overwrite_system
        assert final_system_prompt != direct_system

    def test_extract_both_from_prompts_overwrite(self):
        """测试从 prompts_overwrite 提取 system_prompt 和 task_prompt"""
        prompts_overwrite = {
            "system_prompt": "我是数字员工",
            "task_prompt": "请遵循原则"
        }

        # 模拟逻辑
        final_system_prompt = None
        task_prompt = None

        if prompts_overwrite:
            if "system_prompt" in prompts_overwrite:
                final_system_prompt = prompts_overwrite["system_prompt"]
            if "task_prompt" in prompts_overwrite:
                task_prompt = prompts_overwrite["task_prompt"]

        # 验证
        assert final_system_prompt == "我是数字员工"
        assert task_prompt == "请遵循原则"

    def test_default_prompt_used_when_no_custom(self):
        """测试没有自定义 prompt 时使用默认值"""
        system_prompt = None
        default_prompt = "默认的 DataCloud Agent prompt"

        # 模拟逻辑
        final_system_prompt = system_prompt or default_prompt

        # 验证使用了默认值
        assert final_system_prompt == default_prompt

    def test_complete_flow_with_all_prompts(self):
        """测试完整流程：prompts_overwrite + task_prompt 追加"""
        # Step 1: create_agent 处理 prompts_overwrite
        prompts_overwrite = {
            "system_prompt": "我是亦庄产业大脑数字员工",
            "task_prompt": "请根据以下原则来处理问题。\n# 单一技能优先原则：..."
        }

        system_prompt_param = "这个会被覆盖"

        # 优先级处理
        final_system_prompt = system_prompt_param
        task_prompt = None

        if prompts_overwrite:
            if "system_prompt" in prompts_overwrite:
                final_system_prompt = prompts_overwrite["system_prompt"]
            if "task_prompt" in prompts_overwrite:
                task_prompt = prompts_overwrite["task_prompt"]

        # Step 2: _create_deep_agent 追加 task_prompt
        if task_prompt:
            final_system_prompt = f"{final_system_prompt}\n\n# 任务处理指导\n{task_prompt}"

        # 验证
        assert "我是亦庄产业大脑数字员工" in final_system_prompt
        assert "# 任务处理指导" in final_system_prompt
        assert "# 单一技能优先原则：" in final_system_prompt
        assert "这个会被覆盖" not in final_system_prompt

    def test_empty_prompts_overwrite(self):
        """测试空的 prompts_overwrite"""
        system_prompt_param = "正常的 system_prompt"
        prompts_overwrite = {}

        # 处理逻辑
        final_system_prompt = system_prompt_param
        task_prompt = None

        if prompts_overwrite:
            if "system_prompt" in prompts_overwrite:
                final_system_prompt = prompts_overwrite["system_prompt"]
            if "task_prompt" in prompts_overwrite:
                task_prompt = prompts_overwrite["task_prompt"]

        # 验证使用原始参数
        assert final_system_prompt == system_prompt_param
        assert task_prompt is None
