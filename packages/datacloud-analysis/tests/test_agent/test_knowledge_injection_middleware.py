"""
测试 KnowledgeInjectionMiddleware
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
from datacloud_analysis.middlewares.knowledge_injection import KnowledgeInjectionMiddleware


def _make_request(system_content: str = "", messages=None) -> ModelRequest:
    """Helper: create a minimal ModelRequest mock."""
    req = Mock(spec=ModelRequest)
    req.system_message = SystemMessage(content=system_content) if system_content else None
    req.messages = messages or []
    req.state = {}
    req.override = lambda **kw: Mock(
        system_message=kw.get("system_message", req.system_message),
        messages=req.messages,
        override=req.override,
    )
    return req


class TestKnowledgeInjectionMiddleware:
    """测试知识注入中间件"""

    def test_inherits_agent_middleware(self):
        """测试继承自 AgentMiddleware"""
        middleware = KnowledgeInjectionMiddleware()
        assert isinstance(middleware, AgentMiddleware)

    def test_has_no_tools(self):
        """测试不提供额外工具"""
        middleware = KnowledgeInjectionMiddleware()
        assert middleware.tools == []

    @pytest.mark.asyncio
    async def test_skips_schema_injection_when_not_unified_interface(self, monkeypatch):
        """非 unified_interface 时不注入，直接透传 handler。"""
        monkeypatch.setenv("ONTOLOGY_LOAD_MODE", "mcp")
        middleware = KnowledgeInjectionMiddleware(mounted_objects=["obj_a"])
        request = _make_request("你是一个助手", [HumanMessage(content="查询客户")])
        called = []

        async def mock_handler(req):
            called.append(req)
            return "ok"

        result = await middleware.awrap_model_call(request, mock_handler)
        assert result == "ok"
        assert len(called) == 1
        assert called[0] is request

    @pytest.mark.asyncio
    async def test_retrieve_schema_success(self):
        """测试成功检索 Schema"""
        middleware = KnowledgeInjectionMiddleware()

        mock_result = {
            "term_matches": [
                {"term_name": "客户", "term_type_code": "OBJECT", "match_type": "exact"},
                {"term_name": "订单", "term_type_code": "OBJECT", "match_type": "fuzzy"},
            ]
        }

        with patch("datacloud_analysis.middlewares.knowledge_injection.search_knowledge") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value=mock_result)

            schema = await middleware._retrieve_schema("查询客户订单")

            assert schema is not None
            assert "<ontology_context>" in schema
            assert "客户" in schema
            assert "订单" in schema
            assert "</ontology_context>" in schema

    @pytest.mark.asyncio
    async def test_retrieve_schema_no_matches(self):
        """测试没有匹配的 Schema"""
        middleware = KnowledgeInjectionMiddleware()

        with patch("datacloud_analysis.middlewares.knowledge_injection.search_knowledge") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value={"term_matches": []})

            schema = await middleware._retrieve_schema("随机查询")
            assert schema is None

    @pytest.mark.asyncio
    async def test_awrap_model_call_injects_schema(self):
        """测试 awrap_model_call 注入 Schema 到系统消息"""
        middleware = KnowledgeInjectionMiddleware()

        mock_result = {
            "term_matches": [
                {"term_name": "客户", "term_type_code": "OBJECT", "match_type": "exact"}
            ]
        }

        request = _make_request("你是一个助手", [HumanMessage(content="查询客户")])
        handler_called_with = []

        async def mock_handler(req):
            handler_called_with.append(req)
            return "response"

        with patch("datacloud_analysis.middlewares.knowledge_injection.search_knowledge") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value=mock_result)

            result = await middleware.awrap_model_call(request, mock_handler)

            assert result == "response"
            assert len(handler_called_with) == 1
            # System message should have been updated
            injected_req = handler_called_with[0]
            assert injected_req.system_message is not None

    @pytest.mark.asyncio
    async def test_awrap_model_call_no_user_message(self):
        """测试没有用户消息时跳过注入"""
        middleware = KnowledgeInjectionMiddleware()

        request = _make_request("你是一个助手", [])
        handler_results = []

        async def mock_handler(req):
            handler_results.append(req)
            return "response"

        result = await middleware.awrap_model_call(request, mock_handler)

        assert result == "response"
        # Handler should still be called
        assert len(handler_results) == 1
        # System message unchanged (no injection without query)
        assert handler_results[0].system_message == request.system_message

    @pytest.mark.asyncio
    async def test_awrap_model_call_handles_retrieval_error(self):
        """测试检索失败时不影响正常调用"""
        middleware = KnowledgeInjectionMiddleware()

        request = _make_request("你是一个助手", [HumanMessage(content="查询数据")])
        handler_results = []

        async def mock_handler(req):
            handler_results.append(req)
            return "response"

        with patch("datacloud_analysis.middlewares.knowledge_injection.search_knowledge") as mock_tool:
            mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("连接失败"))

            result = await middleware.awrap_model_call(request, mock_handler)

            # Despite error, handler should still be called
            assert result == "response"
            assert len(handler_results) == 1
