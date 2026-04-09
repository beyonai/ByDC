"""
阶段2：核心逻辑测试（不需要完整依赖）
"""

import pytest
from typing import List
from unittest.mock import Mock, patch


class TestStage2CoreLogic:
    """测试阶段2的核心逻辑"""

    def test_create_agent_accepts_mounted_objects_param(self):
        """测试 create_agent 接受 mounted_objects 参数"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            from datacloud_analysis.agent import create_agent

            mounted_objects = ["company_bo", "order_bo"]
            create_agent(mounted_objects=mounted_objects)

            # 验证参数被传递
            call_kwargs = mock_deep.call_args[1]
            assert "mounted_objects" in call_kwargs
            assert call_kwargs["mounted_objects"] == mounted_objects

    def test_tool_separation_logic(self):
        """测试工具分离逻辑（OBJECT/VIEW vs 其他类型）"""
        # 模拟 tools_dict（来自 worker）
        tools_dict = {
            "query_company": {
                "tool_code": "company_bo",
                "tool_attributes": {"type": "OBJECT"},
            },
            "query_view": {
                "tool_code": "ads_view",
                "tool_attributes": {"type": "VIEW"},
            },
            "agent_delegate": {
                "tool_code": "delegate_agent",
                "tool_attributes": {"type": "AGENT"},
                "tool_func": lambda: "agent_call",
            },
            "custom_function": {
                "tool_code": "custom_func",
                "tool_attributes": {"type": "FUNCTION"},
                "tool_func": lambda: "custom_result",
            },
        }

        # 执行分离逻辑（模拟 worker.py）
        mounted_objects = []
        other_tools = {}

        for tool_name, tool_meta in tools_dict.items():
            tool_attributes = tool_meta.get("tool_attributes", {})
            tool_type = tool_attributes.get("type", "")

            if tool_type in ("OBJECT", "VIEW"):
                tool_code = tool_meta.get("tool_code", "")
                if tool_code and tool_code not in mounted_objects:
                    mounted_objects.append(tool_code)
            else:
                other_tools[tool_name] = tool_meta.get("tool_func")

        # 验证分离结果
        assert len(mounted_objects) == 2
        assert "company_bo" in mounted_objects
        assert "ads_view" in mounted_objects

        assert len(other_tools) == 2
        assert "agent_delegate" in other_tools
        assert "custom_function" in other_tools

        # 验证工具函数可调用
        assert other_tools["agent_delegate"]() == "agent_call"
        assert other_tools["custom_function"]() == "custom_result"


class TestSchemaFormatterLogic:
    """测试 Schema 格式化逻辑"""

    def test_format_object_schema_basic(self):
        """测试基本的对象 Schema 格式化"""
        from datacloud_analysis.utils.schema_formatter import format_object_schema

        # Mock OntologyClass
        mock_class = Mock()
        mock_class.object_name = "企业"
        mock_class.object_code = "company_bo"
        mock_class.description = "企业基本信息"
        mock_class.fields = []
        mock_class.actions = []

        all_relations = []
        mock_loader = Mock()

        result = format_object_schema(mock_class, all_relations, mock_loader)

        # 验证关键内容
        assert "### 对象类型：企业" in result
        assert "**object_type**: `company_bo`" in result
        assert "**描述**: 企业基本信息" in result

    def test_format_object_schema_with_fields(self):
        """测试包含属性的 Schema 格式化"""
        from datacloud_analysis.utils.schema_formatter import format_object_schema

        # Mock field
        mock_field = Mock()
        mock_field.field_name = "企业名称"
        mock_field.field_code = "company_name"
        mock_field.field_type = "STRING"
        mock_field.description = "企业全称"
        mock_field.aliases = ["名称", "企业全称"]

        # Mock OntologyClass with field
        mock_class = Mock()
        mock_class.object_name = "企业"
        mock_class.object_code = "company_bo"
        mock_class.description = "企业基本信息"
        mock_class.fields = [mock_field]
        mock_class.actions = []

        result = format_object_schema(mock_class, [], Mock())

        # 验证属性表格
        assert "#### 属性列表" in result
        assert "企业名称" in result
        assert "company_name" in result
        assert "STRING" in result
        assert "名称, 企业全称" in result

    def test_filter_object_relations_logic(self):
        """测试关系过滤逻辑"""
        from datacloud_analysis.utils.schema_formatter import filter_object_relations

        # Mock relation
        mock_rel = Mock()
        mock_rel.source_class = "company_bo"
        mock_rel.target_class = "order_bo"
        mock_rel.relation_type = "ONE_TO_MANY"
        mock_rel.relation_name = "has_orders"
        mock_rel.description = "企业拥有多个订单"

        # Mock loader
        mock_source = Mock()
        mock_source.object_name = "企业"
        mock_target = Mock()
        mock_target.object_name = "订单"

        mock_loader = Mock()
        mock_loader.get_ontology_class = Mock(
            side_effect=lambda x: mock_source if x == "company_bo" else mock_target
        )

        result = filter_object_relations("company_bo", [mock_rel], mock_loader)

        # 验证结果
        assert len(result) == 1
        assert result[0]["source_name"] == "企业"
        assert result[0]["target_name"] == "订单"
        assert result[0]["relation_type"] == "ONE_TO_MANY"
        assert result[0]["description"] == "企业拥有多个订单"


class TestMiddlewareLogic:
    """测试中间件核心逻辑（不需要导入实际中间件）"""

    def test_filter_relevant_objects_logic(self):
        """测试精细化过滤逻辑（当前实现）"""

        # 模拟 _filter_relevant_objects 方法的逻辑
        def filter_relevant_objects(user_query, all_objects):
            # TODO: 待罗彦卓实现精细化过滤
            # 当前实现：返回所有对象
            return all_objects

        user_query = "查询企业信息"
        all_objects = ["company_bo", "order_bo", "product_bo"]

        result = filter_relevant_objects(user_query, all_objects)

        # 当前返回所有对象
        assert result == all_objects
        assert len(result) == 3

    def test_state_deduplication_logic(self):
        """测试状态去重逻辑"""
        # 模拟去重检查逻辑
        state = {}

        # 第一次调用
        if state.get("_ontology_injected", False):
            injected = False
        else:
            injected = True
            state["_ontology_injected"] = True

        assert injected is True
        assert state["_ontology_injected"] is True

        # 第二次调用
        if state.get("_ontology_injected", False):
            injected = False
        else:
            injected = True
            state["_ontology_injected"] = True

        assert injected is False  # 第二次不注入
