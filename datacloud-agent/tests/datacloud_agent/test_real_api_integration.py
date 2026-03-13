"""
真实API测试 - 使用pytest验证datacloud-agent核心功能

运行方式:
    export OPENAI_API_KEY="your-api-key"
    export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"
    uv run --package datacloud-agent pytest datacloud-agent/tests/test_real_api_integration.py -v

注意: 这些测试需要真实的API密钥，会消耗token
"""

import os
import pytest
from unittest.mock import patch

# 确保环境变量已设置
OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY", "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://lab.iwhalecloud.com/gpt-proxy/v1")


@pytest.fixture(scope="module")
def api_config():
    """提供API配置"""
    return {
        "api_key": OPENAI_API_KEY,
        "base_url": OPENAI_BASE_URL,
        "model": "qwen3.5-plus",  # 使用正确的模型名称格式
    }


@pytest.mark.real_api
class TestModelConfig:
    """真实API测试: 模型配置"""

    def test_create_model_with_real_api(self, api_config):
        """测试使用真实API创建模型"""
        from datacloud_agent.core.model_config import create_model

        model = create_model(api_config)
        assert model is not None
        assert type(model).__name__ == "ChatOpenAI"

    @pytest.mark.asyncio
    async def test_model_invoke_with_real_api(self, api_config):
        """测试使用真实API调用模型"""
        from datacloud_agent.core.model_config import create_model
        from langchain_core.messages import HumanMessage

        model = create_model(api_config)
        result = await model.ainvoke([HumanMessage(content="Say 'test ok'")])

        assert result is not None
        assert result.content is not None
        assert len(result.content) > 0
        print(f"\n模型回复: {result.content}")


@pytest.mark.real_api
class TestTools:
    """真实API测试: 工具系统"""

    def test_get_business_tools(self):
        """测试获取业务工具"""
        from datacloud_agent.core.tools import get_business_tools

        tools = get_business_tools()
        assert len(tools) == 5

        tool_names = [t.name for t in tools]
        assert "know" in tool_names
        assert "query" in tool_names
        assert "compute" in tool_names
        assert "render" in tool_names
        assert "store" in tool_names

    def test_know_tool_invoke(self):
        """测试know工具调用"""
        from datacloud_agent.core.tools import know

        result = know.invoke("什么是数据分析?")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Knowledge" in result or "知识" in result
        print(f"\nknow工具结果: {result[:100]}...")

    def test_query_tool_invoke(self):
        """测试query工具调用"""
        from datacloud_agent.core.tools import query

        result = query.invoke("SELECT * FROM users LIMIT 5")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Query" in result or "查询" in result
        print(f"\nquery工具结果: {result[:100]}...")

    def test_compute_tool_invoke(self):
        """测试compute工具调用"""
        from datacloud_agent.core.tools import compute

        result = compute.invoke("2 + 2")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Compute" in result or "计算" in result
        print(f"\ncompute工具结果: {result[:100]}...")

    def test_store_tool_invoke(self):
        """测试store工具调用"""
        from datacloud_agent.core.tools import store

        result = store.invoke({"key": "test_key", "value": "test_value"})
        assert isinstance(result, str)
        assert "test_key" in result
        assert "test_value" in result
        print(f"\nstore工具结果: {result}")


@pytest.mark.real_api
class TestRegistry:
    """真实API测试: Agent注册表"""

    def test_create_and_register_agent(self):
        """测试创建和注册Agent"""
        from datacloud_agent.core.registry import AgentRegistry, AgentConfig

        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="test-agent",
            provider="openai",
            model="qwen3.5-plus",
            system_prompt="You are a test agent.",
            tools=["know", "query"],
        )

        registry.register("test-agent", config)
        retrieved = registry.get("test-agent")

        assert retrieved is not None
        assert retrieved.agent_id == "test-agent"
        assert retrieved.provider == "openai"
        assert retrieved.model == "qwen3.5-plus"
        assert "know" in retrieved.tools
        assert "query" in retrieved.tools

    def test_create_default_agent(self):
        """测试创建默认Agent"""
        from datacloud_agent.core.registry import AgentRegistry

        registry = AgentRegistry()
        config = registry.create_default_agent("default")

        assert config is not None
        assert config.agent_id == "default"
        assert len(config.tools) == 5
        assert len(config.subagents) == 3
        print(f"\n默认Agent配置:")
        print(f"  - provider: {config.provider}")
        print(f"  - model: {config.model}")
        print(f"  - tools: {len(config.tools)} 个")
        print(f"  - subagents: {len(config.subagents)} 个")


@pytest.mark.real_api
class TestSubagents:
    """真实API测试: 子Agent配置"""

    def test_get_default_subagents(self):
        """测试获取默认子Agent"""
        from datacloud_agent.core.subagents import get_default_subagents

        subagents = get_default_subagents()
        assert len(subagents) == 3

        names = [sa["name"] for sa in subagents]
        assert "researcher" in names
        assert "data_analyst" in names
        assert "visualizer" in names

    def test_convert_to_deepagents_format(self):
        """测试转换为deepagents格式"""
        from datacloud_agent.core.subagents import (
            get_default_subagents,
            convert_to_deepagents_format,
        )

        subagents = get_default_subagents()
        converted = convert_to_deepagents_format(subagents)

        assert len(converted) == 3
        for sa in converted:
            assert "name" in sa
            assert "description" in sa
            assert "system_prompt" in sa


@pytest.mark.real_api
class TestQueueSystem:
    """真实API测试: 队列系统"""

    @pytest.mark.asyncio
    async def test_queue_operations(self):
        """测试队列基本操作"""
        from datacloud_agent.queue.manager import QueueManager
        from datacloud_agent.queue.types import (
            QueueSettings,
            QueuedMessage,
            QueueMode,
            DropPolicy,
        )

        manager = QueueManager()
        settings = QueueSettings(
            mode=QueueMode.COLLECT,
            max_size=100,
            drop_policy=DropPolicy.OLD,
        )

        # 创建队列
        queue = await manager.get_or_create("test-session", settings)
        assert queue is not None
        assert queue.session_key == "test-session"

        # 添加消息
        msg = QueuedMessage(
            prompt="Test message",
            session_key="test-session",
            priority=5,
        )
        success = await manager.enqueue("test-session", msg)
        assert success is True

        # 检查队列大小
        size = await manager.get_size("test-session")
        assert size == 1

        # 出队
        dequeued = await manager.dequeue("test-session")
        assert dequeued is not None
        assert dequeued.prompt == "Test message"


@pytest.mark.real_api
class TestDeepagentsIntegration:
    """真实API测试: deepagents集成"""

    @pytest.mark.asyncio
    async def test_create_deep_agent(self, api_config):
        """测试创建deep agent"""
        from deepagents import create_deep_agent
        from datacloud_agent.core.model_config import create_model

        model = create_model(api_config)
        agent = create_deep_agent(
            model=model,
            system_prompt="你是一个有帮助的助手。",
        )

        assert agent is not None
        assert type(agent).__name__ == "CompiledStateGraph"

    @pytest.mark.asyncio
    async def test_deep_agent_invoke(self, api_config):
        """测试deep agent调用（真实API）"""
        from deepagents import create_deep_agent
        from datacloud_agent.core.model_config import create_model
        from langchain_core.messages import AIMessage

        model = create_model(api_config)
        agent = create_deep_agent(
            model=model,
            system_prompt="你是一个有帮助的助手。",
        )

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "你好，请用一句话介绍自己"}]}
        )

        assert result is not None
        assert "messages" in result
        assert len(result["messages"]) > 0

        last_message = result["messages"][-1]
        content = getattr(last_message, "content", str(last_message))
        assert len(content) > 0

        print(f"\nDeepAgent回复: {content[:100]}...")

        # 验证token使用
        if isinstance(last_message, AIMessage) and last_message.usage_metadata:
            usage = last_message.usage_metadata
            print(
                f"Token使用: input={usage.get('input_tokens')}, "
                f"output={usage.get('output_tokens')}, "
                f"total={usage.get('total_tokens')}"
            )
            assert usage.get("total_tokens", 0) > 0

    @pytest.mark.asyncio
    async def test_deep_agent_with_tools(self, api_config):
        """测试带工具的deep agent"""
        from deepagents import create_deep_agent
        from datacloud_agent.core.model_config import create_model
        from datacloud_agent.core.tools import get_business_tools

        model = create_model(api_config)
        tools = get_business_tools()

        agent = create_deep_agent(
            model=model,
            system_prompt="你是一个有帮助的助手，可以使用工具来回答问题。",
            tools=tools,
        )

        assert agent is not None

        # 测试调用（可能触发工具使用）
        result = await agent.ainvoke({"messages": [{"role": "user", "content": "计算 123 + 456"}]})

        assert result is not None
        assert "messages" in result
        print(f"\n带工具的DeepAgent调用成功，消息数: {len(result['messages'])}")

    @pytest.mark.asyncio
    async def test_deep_agent_with_subagents(self, api_config):
        """测试带子Agent的deep agent"""
        from deepagents import create_deep_agent
        from datacloud_agent.core.model_config import create_model
        from datacloud_agent.core.subagents import get_default_subagents

        model = create_model(api_config)
        subagents = get_default_subagents()

        agent = create_deep_agent(
            model=model,
            system_prompt="你是一个有帮助的助手。",
            subagents=subagents,
        )

        assert agent is not None

        result = await agent.ainvoke({"messages": [{"role": "user", "content": "你好"}]})

        assert result is not None
        print(f"\n带子Agent的DeepAgent调用成功")
