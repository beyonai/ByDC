"""
测试 WorkspaceInitMiddleware
"""

import pytest
from unittest.mock import Mock
from langchain_core.messages import SystemMessage
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
from datacloud_analysis.middlewares.workspace_init import WorkspaceInitMiddleware


def _make_request(system_content: str = "") -> ModelRequest:
    """Helper: create a minimal ModelRequest mock."""
    req = Mock(spec=ModelRequest)
    req.system_message = SystemMessage(content=system_content) if system_content else None
    req.messages = []
    captured = {}

    def override(**kw):
        captured["system_message"] = kw.get("system_message", req.system_message)
        new_req = Mock(spec=ModelRequest)
        new_req.system_message = captured["system_message"]
        new_req.messages = req.messages
        new_req.override = req.override
        return new_req

    req.override = override
    return req


class TestWorkspaceInitMiddleware:
    """测试工作区初始化中间件"""

    def test_inherits_agent_middleware(self):
        """测试继承自 AgentMiddleware"""
        middleware = WorkspaceInitMiddleware(workspace_dir="/tmp/workspace")
        assert isinstance(middleware, AgentMiddleware)

    def test_middleware_initialization(self):
        """测试中间件初始化"""
        middleware = WorkspaceInitMiddleware(
            workspace_dir="/tmp/workspace",
            agent_name="TestAgent"
        )
        assert middleware.workspace_dir == "/tmp/workspace"
        assert middleware.agent_name == "TestAgent"

    def test_middleware_default_agent_name(self):
        """测试默认 agent 名称"""
        middleware = WorkspaceInitMiddleware(workspace_dir="/tmp/workspace")
        assert middleware.agent_name == "DataCloud Agent"

    def test_has_no_tools(self):
        """测试不提供额外工具"""
        middleware = WorkspaceInitMiddleware(workspace_dir="/tmp/workspace")
        assert middleware.tools == []

    def test_wrap_model_call_injects_workspace_info(self):
        """测试 wrap_model_call 注入工作区信息"""
        middleware = WorkspaceInitMiddleware(
            workspace_dir="/tmp/workspace",
            agent_name="TestAgent"
        )

        request = _make_request("你是一个助手")
        handler_called_with = []

        def mock_handler(req):
            handler_called_with.append(req)
            return "response"

        result = middleware.wrap_model_call(request, mock_handler)

        assert result == "response"
        assert len(handler_called_with) == 1
        injected = handler_called_with[0].system_message
        assert injected is not None
        content_text = _extract_text(injected)
        assert "TestAgent" in content_text
        assert "/tmp/workspace" in content_text

    def test_wrap_model_call_only_injects_once(self):
        """测试工作区信息只注入一次"""
        middleware = WorkspaceInitMiddleware(workspace_dir="/tmp/workspace")

        calls = []

        def mock_handler(req):
            calls.append(req.system_message)
            return "response"

        r1 = _make_request("第一次")
        middleware.wrap_model_call(r1, mock_handler)
        r2 = _make_request("第二次")
        middleware.wrap_model_call(r2, mock_handler)

        assert len(calls) == 2
        # First call should have workspace injected, second should not change
        first_content = _extract_text(calls[0])
        assert "/tmp/workspace" in first_content
        # Second call: _injected is already True, request passed as-is
        second_content = _extract_text(calls[1])
        assert "/tmp/workspace" not in second_content

    @pytest.mark.asyncio
    async def test_awrap_model_call_injects_workspace_info(self):
        """测试异步版本注入工作区信息"""
        middleware = WorkspaceInitMiddleware(
            workspace_dir="/tmp/workspace",
            agent_name="TestAgent"
        )

        request = _make_request("你是一个助手")
        handler_called_with = []

        async def mock_handler(req):
            handler_called_with.append(req)
            return "response"

        result = await middleware.awrap_model_call(request, mock_handler)

        assert result == "response"
        assert len(handler_called_with) == 1
        injected = handler_called_with[0].system_message
        assert injected is not None
        content_text = _extract_text(injected)
        assert "TestAgent" in content_text
        assert "/tmp/workspace" in content_text


def _extract_text(system_message) -> str:
    """Extract text from SystemMessage content."""
    if system_message is None:
        return ""
    content = system_message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)
