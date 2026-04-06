"""
阶段3：统一 query_objects 工具 - 测试
"""

import pytest
from unittest.mock import Mock, patch


class TestStage3QueryObjectsUnification:
    """测试阶段3的 query_objects 统一参数功能"""

    def test_query_objects_uses_object_type_parameter(self):
        """测试 query_objects 使用 object_type 参数"""
        from datacloud_analysis.tools.oql.query_objects import query_objects

        # 验证函数签名包含 object_type 参数
        import inspect
        sig = inspect.signature(query_objects.func)
        params = list(sig.parameters.keys())

        assert "object_type" in params
        assert params[0] == "object_type"  # 第一个参数

    def test_object_type_parameter_is_required(self):
        """测试 object_type 参数是必填的"""
        from datacloud_analysis.tools.oql.query_objects import query_objects

        import inspect
        sig = inspect.signature(query_objects.func)
        object_type_param = sig.parameters["object_type"]

        # 验证没有默认值（必填）
        assert object_type_param.default == inspect.Parameter.empty

    @patch("datacloud_analysis.tools.oql.query_objects.get_oql_router")
    @patch("datacloud_analysis.tools.oql.query_objects.get_term_resolver")
    @patch("datacloud_analysis.tools.oql.query_objects.get_executor")
    @patch("datacloud_analysis.tools.oql.query_objects.get_datasource_registry")
    def test_query_objects_calls_router_with_object_param(
        self, mock_ds_reg, mock_executor, mock_resolver, mock_router
    ):
        """测试 query_objects 调用 router 时使用 'object' 参数"""
        from datacloud_analysis.tools.oql.query_objects import query_objects

        # Mock router
        mock_router_instance = Mock()
        mock_router_instance.route.return_value = []
        mock_router.return_value = mock_router_instance

        mock_resolver.return_value = Mock()
        mock_executor.return_value = Mock()
        mock_ds_reg.return_value = Mock()

        # 调用 query_objects
        query_objects.func(object_type="company_bo", limit=10)

        # 验证 router.route 被调用
        assert mock_router_instance.route.called
        call_args = mock_router_instance.route.call_args
        oql_params = call_args[1]["oql_params"]

        # 验证 oql_params 包含 "object" 字段
        assert "object" in oql_params
        assert oql_params["object"] == "company_bo"


class TestStage3RouterObjectResolution:
    """测试 OqlRouter 的对象解析逻辑"""

    def test_router_resolves_object_from_registry(self):
        """测试 router 从注册表解析对象"""
        from datacloud_data_sdk.oql.adapter import resolve_object
        from datacloud_data_sdk.oql.models import OQLError

        # Mock registry
        mock_registry = Mock()
        mock_class = Mock()
        mock_class.object_code = "company_bo"
        mock_registry.get_class.return_value = mock_class

        # 调用 resolve_object
        result = resolve_object("company_bo", mock_registry)

        assert result == mock_class
        mock_registry.get_class.assert_called_once_with("company_bo")

    def test_router_raises_error_for_unknown_object(self):
        """测试 router 对未知对象抛出错误"""
        from datacloud_data_sdk.oql.adapter import resolve_object
        from datacloud_data_sdk.oql.models import OQLError

        # Mock registry 返回 None
        mock_registry = Mock()
        mock_registry.get_class.return_value = None

        # 验证抛出 OQLError
        with pytest.raises(OQLError) as exc_info:
            resolve_object("unknown_object", mock_registry)

        assert "不存在" in str(exc_info.value)


class TestStage3UnifiedBehavior:
    """测试对象和视图的统一行为"""

    @patch("datacloud_analysis.tools.oql.query_objects.get_oql_router")
    @patch("datacloud_analysis.tools.oql.query_objects.get_term_resolver")
    @patch("datacloud_analysis.tools.oql.query_objects.get_executor")
    @patch("datacloud_analysis.tools.oql.query_objects.get_datasource_registry")
    def test_query_objects_handles_both_object_and_view(
        self, mock_ds_reg, mock_executor, mock_resolver, mock_router
    ):
        """测试 query_objects 统一处理对象和视图"""
        from datacloud_analysis.tools.oql.query_objects import query_objects

        # Mock router
        mock_router_instance = Mock()
        mock_router_instance.route.return_value = [
            {"id": "1", "name": "测试数据"}
        ]
        mock_router.return_value = mock_router_instance

        mock_resolver.return_value = Mock()
        mock_executor.return_value = Mock()
        mock_ds_reg.return_value = Mock()

        # 测试对象查询
        result1 = query_objects.func(object_type="company_bo", limit=10)
        assert result1["status"] == "success"

        # 测试视图查询
        result2 = query_objects.func(object_type="ads_analysis_view", limit=10)
        assert result2["status"] == "success"

        # 验证两次调用都使用相同的参数结构
        calls = mock_router_instance.route.call_args_list
        assert len(calls) == 2

        # 两次调用的参数结构应该一致
        params1 = calls[0][1]["oql_params"]
        params2 = calls[1][1]["oql_params"]

        assert "object" in params1
        assert "object" in params2
        assert params1["object"] == "company_bo"
        assert params2["object"] == "ads_analysis_view"
