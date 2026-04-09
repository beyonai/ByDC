"""
阶段4：思考过程推送 - 测试
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestStage4ToolLoggingMiddleware:
    """测试阶段4的工具调用日志中间件"""

    @patch("datacloud_analysis.middlewares.tool_logging.logger")
    def test_middleware_initialization(self, mock_logger):
        """测试中间件初始化"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        assert middleware is not None
        assert hasattr(middleware, "awrap_tool_call")

    @pytest.mark.asyncio
    async def test_awrap_tool_call_without_gateway_context(self):
        """测试没有 gateway_context 时直接执行工具"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # Mock request without gateway_context
        mock_request = Mock()
        mock_request.runtime.config.get.return_value = {}
        mock_request.tool_call = {"name": "test_tool", "args": {}}

        # Mock handler
        mock_handler = AsyncMock(return_value="result")

        # 调用 awrap_tool_call
        result = await middleware.awrap_tool_call(mock_request, mock_handler)

        # 验证直接调用 handler
        assert result == "result"
        mock_handler.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_awrap_tool_call_with_gateway_context(self):
        """测试有 gateway_context 时推送工具调用信息"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # Mock gateway_context
        mock_gateway_context = Mock()
        mock_gateway_context.message_id = "parent_msg_123"
        mock_gateway_context.generate_message_id = Mock(return_value="child_msg_456")
        mock_gateway_context.emit_chunk = AsyncMock()

        # Mock sub_step context manager
        mock_sub_step_cm = MagicMock()
        mock_sub_step_cm.__aenter__ = AsyncMock()
        mock_sub_step_cm.__aexit__ = AsyncMock()
        mock_gateway_context.sub_step = Mock(return_value=mock_sub_step_cm)

        # Mock request with gateway_context
        mock_request = Mock()
        mock_request.runtime.config = {"configurable": {"gateway_context": mock_gateway_context}}
        mock_request.tool_call = {"name": "query_objects", "args": {"object_type": "company_bo"}}
        mock_request.tool = Mock()
        mock_request.tool._is_agent_delegate = False

        # Mock handler
        mock_handler = AsyncMock(return_value={"status": "success", "result": {"records": []}})

        # 调用 awrap_tool_call
        result = await middleware.awrap_tool_call(mock_request, mock_handler)

        # 验证结果
        assert result["status"] == "success"

        # 验证 sub_step 被调用
        mock_gateway_context.sub_step.assert_called_once_with("query_objects")

        # 验证 emit_chunk 被调用（入参和出参）
        assert mock_gateway_context.emit_chunk.call_count >= 2


class TestStage4ToolLoggingLogic:
    """测试工具日志逻辑"""

    def test_is_agent_delegate_tool_detection(self):
        """测试 AGENT 类型工具检测"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # Mock AGENT 类型工具
        mock_request_agent = Mock()
        mock_request_agent.tool = Mock()
        mock_request_agent.tool._is_agent_delegate = True

        assert middleware._is_agent_delegate_tool(mock_request_agent) is True

        # Mock 普通工具
        mock_request_normal = Mock()
        mock_request_normal.tool = Mock()
        mock_request_normal.tool._is_agent_delegate = False

        assert middleware._is_agent_delegate_tool(mock_request_normal) is False

    def test_format_args_basic(self):
        """测试入参格式化"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # 空参数
        assert middleware._format_args({}) == "{}"

        # 简单参数
        args = {"object_type": "company_bo", "limit": 10}
        result = middleware._format_args(args)
        assert "object_type" in result
        assert "company_bo" in result

    def test_format_args_truncation(self):
        """测试入参格式化截断"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # 超长参数
        long_args = {"data": "x" * 1000}
        result = middleware._format_args(long_args)
        assert len(result) <= 520  # 500 + "... (已截断)"
        assert "已截断" in result

    def test_format_result_with_status(self):
        """测试返回结果格式化（包含 status）"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # 成功结果
        result = {"status": "success", "result": {"records": [{"id": "1"}, {"id": "2"}]}}
        formatted = middleware._format_result(result)
        assert "success" in formatted
        assert "2" in formatted  # 记录数

    def test_format_result_generic(self):
        """测试返回结果格式化（通用）"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # 通用结果
        result = {"data": "test"}
        formatted = middleware._format_result(result)
        assert "test" in formatted


class TestStage4MiddlewareRegistration:
    """测试中间件注册"""

    def test_tool_logging_middleware_imported(self):
        """测试 ToolCallLoggingMiddleware 可以导入"""
        from datacloud_analysis.middlewares import ToolCallLoggingMiddleware

        assert ToolCallLoggingMiddleware is not None

    @patch("datacloud_analysis.agent.create_deep_agent")
    @patch("datacloud_analysis.agent.pathlib.Path")
    @patch("datacloud_analysis.session.checkpointer.get_checkpointer")
    @patch("datacloud_analysis.backend.create_datacloud_backend")
    @patch("datacloud_analysis.tools.registry.register_all_tools")
    def test_middleware_registered_in_agent(
        self, mock_reg, mock_backend, mock_checkpointer, mock_path, mock_create
    ):
        """测试中间件在 agent 中注册"""
        mock_reg.return_value = []
        mock_backend.return_value = Mock()
        mock_checkpointer.return_value = Mock()
        mock_create.return_value = Mock()

        # Mock pathlib.Path
        mock_path_instance = Mock()
        mock_path_instance.parent = Mock()
        mock_path.return_value = mock_path_instance

        from datacloud_analysis.agent import _create_deep_agent

        _create_deep_agent(mounted_objects=["company_bo"])

        # 验证 create_deep_agent 被调用
        assert mock_create.called

        # 获取 middleware 参数
        call_kwargs = mock_create.call_args[1]
        middlewares = call_kwargs.get("middleware", [])

        # 验证包含 ToolCallLoggingMiddleware
        from datacloud_analysis.middlewares import ToolCallLoggingMiddleware

        middleware_types = [type(m).__name__ for m in middlewares]
        assert "ToolCallLoggingMiddleware" in middleware_types


class TestStage4MessageIdGeneration:
    """测试 message_id 生成逻辑"""

    def test_new_message_id_with_generator(self):
        """测试使用 generate_message_id 生成 message_id"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # Mock gateway_context with generate_message_id
        mock_gateway_context = Mock()
        mock_gateway_context.generate_message_id = Mock(return_value="msg_789")

        message_id = middleware._new_message_id(mock_gateway_context)

        assert message_id == "msg_789"
        mock_gateway_context.generate_message_id.assert_called_once()

    def test_new_message_id_without_generator(self):
        """测试没有 generate_message_id 时返回空字符串"""
        from datacloud_analysis.middlewares.tool_logging import ToolCallLoggingMiddleware

        middleware = ToolCallLoggingMiddleware()

        # Mock gateway_context without generate_message_id
        mock_gateway_context = Mock(spec=[])

        message_id = middleware._new_message_id(mock_gateway_context)

        assert message_id == ""
