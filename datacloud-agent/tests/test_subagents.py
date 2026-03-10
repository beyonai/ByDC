"""Tests for subagents module"""

from datacloud_agent.core.subagents import (
    SubAgentConfig,
    get_default_subagents,
    convert_to_deepagents_format,
)


def test_subagent_config_creation():
    """测试子Agent配置创建"""
    config = SubAgentConfig(
        name="test_agent",
        description="Test agent",
        system_prompt="You are a test agent.",
    )
    assert config.name == "test_agent"
    assert config.tools is None


def test_get_default_subagents():
    """测试获取默认子Agent配置"""
    subagents = get_default_subagents()
    assert len(subagents) == 3

    names = [sa["name"] for sa in subagents]
    assert "researcher" in names
    assert "data_analyst" in names
    assert "visualizer" in names


def test_convert_to_deepagents_format():
    """测试配置格式转换"""
    configs = [
        SubAgentConfig(
            name="test",
            description="Test",
            system_prompt="Test prompt",
        )
    ]

    result = convert_to_deepagents_format(configs)
    assert len(result) == 1
    assert result[0]["name"] == "test"
    assert "tools" not in result[0]


def test_convert_with_dict_input():
    """测试字典输入"""
    configs = [{"name": "dict_agent", "description": "Dict", "system_prompt": "Prompt"}]
    result = convert_to_deepagents_format(configs)
    assert result == configs
