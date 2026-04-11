"""TDD：删除 IntentClassifier — 验证 intend_node 不再调用 LLM 意图分类。

覆盖范围：
1. intend_node 普通查询路径下，IntentClassifier.classify 永不被调用
2. 即使配置了 DATACLOUD_LLM_QUICK_* 环境变量，也不触发 LLM 调用
3. 普通查询始终返回 intent="react"，execution_status="execution"
4. CommandRouter 仍然正常工作（删除 classifier 不影响命令路由）
5. user_query 仍正确取最后一条 HumanMessage 的内容
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# 1. classify() 永远不被调用
# ---------------------------------------------------------------------------

class TestIntentClassifierNeverCalled:
    """删除后，intend_node 不应再有 IntentClassifier 相关属性或调用。"""

    def test_classifier_attribute_removed_from_node_module(self) -> None:
        """node 模块中不应再存在 _classifier 属性。"""
        import datacloud_analysis.orchestration.intend.node as node_module

        assert not hasattr(node_module, "_classifier"), (
            "_classifier 应已从 node 模块删除，但仍然存在"
        )

    def test_intent_classifier_not_imported_in_node_module(self) -> None:
        """node 模块中不应再导入 IntentClassifier。"""
        import datacloud_analysis.orchestration.intend.node as node_module

        assert not hasattr(node_module, "IntentClassifier"), (
            "IntentClassifier 应已从 node 模块移除，但仍被导入"
        )

    @pytest.mark.asyncio
    async def test_regular_query_succeeds_without_classifier(self) -> None:
        """普通查询路径无需 classifier，直接返回 react。"""
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="查询本季度销售额")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["intent"] == "react"
        assert result["execution_status"] == "execution"

    @pytest.mark.asyncio
    async def test_chitchat_query_also_returns_react(self) -> None:
        """闲聊类查询（未被 worker 拦截时）也直接返回 react，不做 LLM 分类。"""
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="你好")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["intent"] == "react"


# ---------------------------------------------------------------------------
# 2. 即使配置了 DATACLOUD_LLM_QUICK_*，也不触发 LLM 网络调用
# ---------------------------------------------------------------------------

class TestNoLlmCallEvenWithQuickEnv:
    """配置了快速 LLM 环境变量时，intend_node 依然不触发任何 LLM 调用。"""

    @pytest.mark.asyncio
    async def test_no_init_chat_model_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """即使配置了 QUICK 环境变量，intend_node 也不触发任何 LLM 调用。

        intent_classifier.py 已删除，node.py 不再引用 init_chat_model；
        直接验证结果正确即可（无需 patch 已不存在的模块）。
        """
        monkeypatch.setenv("DATACLOUD_LLM_QUICK_API_BASE", "http://fake-llm:8080/v1")
        monkeypatch.setenv("DATACLOUD_LLM_QUICK_API_KEY", "fake-key-123")
        monkeypatch.setenv("DATACLOUD_LLM_QUICK_MODEL", "fake-gpt")

        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="查询库存数量")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            # intent_classifier.py 已删除，直接调用不会触发任何 LLM 网络请求
            result = await intend_node(state, config)

        assert result["intent"] == "react"
        assert result["execution_status"] == "execution"


# ---------------------------------------------------------------------------
# 3. 普通查询始终返回 intent="react"，不依赖 LLM
# ---------------------------------------------------------------------------

class TestIntentAlwaysReact:
    """删除 classifier 后，非命令查询的 intent 应固定为 react。"""

    @pytest.mark.asyncio
    async def test_regular_query_returns_react_intent(self) -> None:
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="请分析销售趋势")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["intent"] == "react"
        assert result["execution_status"] == "execution"

    @pytest.mark.asyncio
    async def test_react_intent_returned_without_any_llm_mock(self) -> None:
        """不 mock 任何 LLM，intend_node 也应正常返回 react，不抛出异常。"""
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="查询产品列表")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            # 不 mock 任何 LLM — 如果内部仍然调用 LLM 会因为无法连接而失败
            result = await intend_node(state, config)

        assert result["intent"] == "react"


# ---------------------------------------------------------------------------
# 4. CommandRouter 仍然正常工作
# ---------------------------------------------------------------------------

class TestCommandRouterStillWorks:
    """删除 IntentClassifier 不影响 CommandRouter 的命令路由功能。"""

    @pytest.mark.asyncio
    async def test_json_command_still_routes_to_command_done(self) -> None:
        import json
        from datacloud_analysis.orchestration.intend.node import intend_node

        cmd_msg = HumanMessage(content=json.dumps({"command": "get_file", "page": 2}))
        state: dict[str, Any] = {"messages": [cmd_msg]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(True, {"data": "page2"}))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["execution_status"] == "command_done"
        assert result["intent"] == "command"

    @pytest.mark.asyncio
    async def test_command_route_short_circuits_to_command_done(self) -> None:
        """命令路由短路后，直接返回 command_done，不进入 react 路径。"""
        import json
        from datacloud_analysis.orchestration.intend.node import intend_node

        cmd_msg = HumanMessage(content=json.dumps({"command": "update_terms"}))
        state: dict[str, Any] = {"messages": [cmd_msg]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(True, {}))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["execution_status"] == "command_done"
        assert result["intent"] == "command"


# ---------------------------------------------------------------------------
# 5. user_query 仍正确取最后一条 HumanMessage
# ---------------------------------------------------------------------------

class TestUserQueryExtraction:
    """删除 classifier 后，user_query 提取逻辑不变。"""

    @pytest.mark.asyncio
    async def test_user_query_is_last_human_message(self) -> None:
        """多轮消息中，user_query 应为最后一条 HumanMessage 的内容。"""
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="第一个问题"),
                AIMessage(content="助手回复"),
                HumanMessage(content="第二个问题"),
                AIMessage(content="助手再次回复"),
            ]
        }
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["user_query"] == "第二个问题"

    @pytest.mark.asyncio
    async def test_user_query_not_from_trailing_ai_message(self) -> None:
        """末尾是 AIMessage 时，user_query 不能误取 AI 的内容。"""
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="用户真实问题"),
                AIMessage(content="AI 回复，不应成为 user_query"),
            ]
        }
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["user_query"] == "用户真实问题"
        assert "AI 回复" not in result["user_query"]
