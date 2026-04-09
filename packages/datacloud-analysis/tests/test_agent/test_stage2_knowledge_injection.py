"""
阶段2：工具类型分离与知识注入 - 测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datacloud_analysis.agent import create_agent


class TestStage2ToolSeparation:
    """测试阶段2的工具类型分离功能"""

    def test_create_agent_accepts_mounted_objects(self):
        """测试 create_agent 接受 mounted_objects 参数"""
        with patch("datacloud_analysis.agent._create_deep_agent") as mock_deep:
            mock_deep.return_value = Mock()

            mounted_objects = ["company_bo", "order_bo"]
            create_agent(mounted_objects=mounted_objects)

            call_kwargs = mock_deep.call_args[1]
            assert call_kwargs["mounted_objects"] == mounted_objects

    @patch("datacloud_analysis.middlewares.knowledge_injection.HumanMessage")
    @patch("datacloud_analysis.agent.CODE_EXECUTOR_SUBAGENT", Mock())
    def test_mounted_objects_passed_to_middleware(self, mock_human_msg):
        """测试 mounted_objects 传递给 KnowledgeInjectionMiddleware"""
        with patch("datacloud_analysis.agent.pathlib.Path") as mock_path:
            with patch(
                "datacloud_analysis.session.checkpointer.get_checkpointer"
            ) as mock_checkpointer:
                with patch("deepagents.create_deep_agent") as mock_create:
                    with patch("datacloud_analysis.backend.create_datacloud_backend"):
                        with patch(
                            "datacloud_analysis.tools.registry.register_all_tools"
                        ) as mock_reg:
                            with patch(
                                "datacloud_analysis.middlewares.KnowledgeInjectionMiddleware"
                            ) as mock_mid:
                                mock_reg.return_value = []
                                mock_checkpointer.return_value = Mock()
                                mock_create.return_value = Mock()

                                # Mock pathlib.Path behavior
                                mock_path_instance = Mock()
                                mock_path_instance.parent = Mock()
                                mock_path.return_value = mock_path_instance

                                from datacloud_analysis.agent import _create_deep_agent

                                mounted_objects = ["company_bo", "order_bo"]
                                _create_deep_agent(mounted_objects=mounted_objects, locale="zh_CN")

                                # 验证 KnowledgeInjectionMiddleware 被调用，并传入 mounted_objects
                                mock_mid.assert_called_once_with(mounted_objects=mounted_objects)


class TestKnowledgeInjectionLogic:
    """测试知识注入逻辑"""

    @patch("datacloud_analysis.middlewares.knowledge_injection.HumanMessage")
    def test_filter_relevant_objects_returns_all_objects(self, mock_human_msg):
        """测试 _filter_relevant_objects 当前返回所有对象"""
        from datacloud_analysis.middlewares.knowledge_injection import KnowledgeInjectionMiddleware

        middleware = KnowledgeInjectionMiddleware(
            mounted_objects=["company_bo", "order_bo", "product_bo"]
        )

        user_query = "查询企业信息"
        all_objects = ["company_bo", "order_bo", "product_bo"]

        # 当前实现返回所有对象（TODO 待罗彦卓实现精细化过滤）
        relevant = middleware._filter_relevant_objects(user_query, all_objects)

        assert relevant == all_objects

    @patch("datacloud_analysis.middlewares.knowledge_injection.HumanMessage")
    def test_middleware_initialized_with_mounted_objects(self, mock_human_msg):
        """测试中间件正确初始化"""
        from datacloud_analysis.middlewares.knowledge_injection import KnowledgeInjectionMiddleware

        mounted_objects = ["company_bo", "order_bo"]
        middleware = KnowledgeInjectionMiddleware(mounted_objects=mounted_objects)

        assert middleware.mounted_objects == mounted_objects

    @patch("datacloud_analysis.middlewares.knowledge_injection.HumanMessage")
    def test_middleware_initialized_without_mounted_objects(self, mock_human_msg):
        """测试中间件无挂载对象时初始化"""
        from datacloud_analysis.middlewares.knowledge_injection import KnowledgeInjectionMiddleware

        middleware = KnowledgeInjectionMiddleware()

        assert middleware.mounted_objects == []


class TestSchemaFormatter:
    """测试 Schema 格式化函数"""

    def test_format_object_schema_basic_structure(self):
        """测试格式化对象 Schema 的基本结构"""
        from datacloud_analysis.utils.schema_formatter import format_object_schema

        # Mock OntologyClass
        mock_class = Mock()
        mock_class.object_name = "企业"
        mock_class.object_code = "company_bo"
        mock_class.description = "企业基本信息"
        mock_class.fields = []
        mock_class.actions = []

        # Mock relations and loader
        all_relations = []
        mock_loader = Mock()

        result = format_object_schema(mock_class, all_relations, mock_loader)

        # 验证包含基本信息
        assert "### 对象类型：企业" in result
        assert "**object_type**: `company_bo`" in result
        assert "**描述**: 企业基本信息" in result

    def test_format_object_schema_with_fields(self):
        """测试格式化对象 Schema 包含属性"""
        from datacloud_analysis.utils.schema_formatter import format_object_schema

        # Mock field
        mock_field = Mock()
        mock_field.field_name = "企业名称"
        mock_field.field_code = "company_name"
        mock_field.field_type = "STRING"
        mock_field.description = "企业全称"
        mock_field.aliases = ["名称", "企业全称"]

        # Mock OntologyClass
        mock_class = Mock()
        mock_class.object_name = "企业"
        mock_class.object_code = "company_bo"
        mock_class.description = "企业基本信息"
        mock_class.fields = [mock_field]
        mock_class.actions = []

        all_relations = []
        mock_loader = Mock()

        result = format_object_schema(mock_class, all_relations, mock_loader)

        # 验证包含属性列表
        assert "#### 属性列表" in result
        assert "企业名称" in result
        assert "company_name" in result
        assert "STRING" in result

    def test_filter_object_relations(self):
        """测试过滤对象关系"""
        from datacloud_analysis.utils.schema_formatter import filter_object_relations

        # Mock relation
        mock_rel = Mock()
        mock_rel.source_class = "company_bo"
        mock_rel.target_class = "order_bo"
        mock_rel.relation_type = "ONE_TO_MANY"
        mock_rel.relation_name = "has_orders"
        mock_rel.description = "企业拥有多个订单"

        all_relations = [mock_rel]

        # Mock loader
        mock_loader = Mock()
        mock_source = Mock()
        mock_source.object_name = "企业"
        mock_target = Mock()
        mock_target.object_name = "订单"

        mock_loader.get_ontology_class = Mock(
            side_effect=lambda x: mock_source if x == "company_bo" else mock_target
        )

        result = filter_object_relations("company_bo", all_relations, mock_loader)

        assert len(result) == 1
        assert result[0]["source_name"] == "企业"
        assert result[0]["target_name"] == "订单"
        assert result[0]["relation_type"] == "ONE_TO_MANY"


class TestToolTypeLogic:
    """测试工具类型分离逻辑"""

    def test_separate_object_view_from_other_tools(self):
        """测试分离 OBJECT/VIEW 类型和其他类型工具"""
        # 模拟 tools_dict
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

        # 分离逻辑（模拟 worker.py 中的代码）
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
        assert "company_bo" in mounted_objects
        assert "ads_view" in mounted_objects
        assert len(mounted_objects) == 2

        assert "agent_delegate" in other_tools
        assert "custom_function" in other_tools
        assert len(other_tools) == 2

        # 验证工具函数可调用
        assert other_tools["agent_delegate"]() == "agent_call"
        assert other_tools["custom_function"]() == "custom_result"
