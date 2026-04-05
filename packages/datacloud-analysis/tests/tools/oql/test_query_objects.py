"""
QueryObjects 工具单元测试
"""

import pytest
from unittest.mock import Mock, patch
from datacloud_analysis.tools.oql.query_objects import query_objects
from datacloud_data_sdk.oql import OQLError, OQLErrorCode


@pytest.fixture
def mock_dependencies():
    """Mock 依赖注入"""
    with patch("datacloud_analysis.tools.oql.query_objects.get_oql_router") as mock_router, \
         patch("datacloud_analysis.tools.oql.query_objects.get_term_resolver") as mock_term, \
         patch("datacloud_analysis.tools.oql.query_objects.get_executor") as mock_exec, \
         patch("datacloud_analysis.tools.oql.query_objects.get_datasource_registry") as mock_ds:

        router = Mock()
        mock_router.return_value = router
        mock_term.return_value = Mock()
        mock_exec.return_value = Mock()
        mock_ds.return_value = Mock()

        yield router


class TestQueryObjects:
    """QueryObjects 工具测试"""

    def test_basic_query(self, mock_dependencies):
        """测试基本查询"""
        mock_dependencies.route.return_value = [
            {"姓名": "张三", "部门": "技术部", "薪资": 10000},
            {"姓名": "李四", "部门": "技术部", "薪资": 12000},
        ]

        result = query_objects.invoke({
            "object_type": "员工",
            "select": ["姓名", "部门", "薪资"],
            "where": [{"field": "部门", "op": "eq", "value": "技术部"}],
            "limit": 20,
        })

        assert result["status"] == "success"
        assert result["tool"] == "QueryObjects"
        assert result["result"]["columns"] == ["姓名", "部门", "薪资"]
        assert len(result["result"]["rows"]) == 2
        assert result["result"]["rows"][0] == ["张三", "技术部", 10000]
        assert result["result"]["returned"] == 2
        assert result["result"]["pagination"]["limit"] == 20

        # 验证调用参数
        mock_dependencies.route.assert_called_once()
        call_args = mock_dependencies.route.call_args[1]
        assert call_args["oql_params"]["object"] == "员工"
        assert call_args["oql_params"]["fields"] == ["姓名", "部门", "薪资"]
        assert call_args["oql_params"]["limit"] == 20

    def test_aggregation_query(self, mock_dependencies):
        """测试聚合查询"""
        mock_dependencies.route.return_value = [
            {"部门": "技术部", "总薪资": 50000, "人数": 5},
            {"部门": "产品部", "总薪资": 40000, "人数": 4},
        ]

        result = query_objects.invoke({
            "object_type": "员工",
            "metrics": [
                {"field": "薪资", "aggregation": "sum", "alias": "总薪资"},
                {"field": "员工ID", "aggregation": "count", "alias": "人数"},
            ],
            "group_by": [{"field": "部门"}],
        })

        assert result["status"] == "success"
        assert result["result"]["columns"] == ["部门", "总薪资", "人数"]
        assert len(result["result"]["rows"]) == 2

    def test_include_links(self, mock_dependencies):
        """测试关系漫游"""
        mock_dependencies.route.return_value = [
            {
                "订单号": "ORD001",
                "金额": 1000,
                "客户__客户名称": "张三",
                "客户__联系电话": "13800138000",
            }
        ]

        result = query_objects.invoke({
            "object_type": "订单",
            "select": ["订单号", "金额"],
            "include_links": [
                {"relation": "订单_客户", "fields": ["客户名称", "联系电话"]}
            ],
        })

        assert result["status"] == "success"
        assert "客户__客户名称" in result["result"]["columns"]

    def test_empty_result(self, mock_dependencies):
        """测试空结果"""
        mock_dependencies.route.return_value = []

        result = query_objects.invoke({
            "object_type": "员工",
            "where": [{"field": "部门", "op": "eq", "value": "不存在的部门"}],
        })

        assert result["status"] == "success"
        assert result["result"]["columns"] == []
        assert result["result"]["rows"] == []
        assert result["result"]["returned"] == 0
        assert result["result"]["pagination"]["has_next"] is False

    def test_oql_error_handling(self, mock_dependencies):
        """测试 OQL 错误处理"""
        mock_dependencies.route.side_effect = OQLError(
            OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
            "对象 'Employee' 不存在",
            {"object_type": "Employee"},
        )

        result = query_objects.invoke({"object_type": "Employee"})

        assert result["status"] == "error"
        assert result["error_code"] == "OQL_ERR_UNKNOWN_OBJECT"
        assert "不存在" in result["message"]

    def test_unexpected_error_handling(self, mock_dependencies):
        """测试未预期异常处理"""
        mock_dependencies.route.side_effect = ValueError("意外错误")

        result = query_objects.invoke({"object_type": "员工"})

        assert result["status"] == "error"
        assert result["error_code"] == "INTERNAL_ERROR"
        assert "意外错误" in result["message"]

    def test_pagination(self, mock_dependencies):
        """测试分页"""
        mock_dependencies.route.return_value = [
            {"id": i, "name": f"Item{i}"} for i in range(20)
        ]

        result = query_objects.invoke({
            "object_type": "测试对象",
            "limit": 20,
            "offset": 0,
        })

        assert result["result"]["pagination"]["limit"] == 20
        assert result["result"]["pagination"]["offset"] == 0
        assert result["result"]["pagination"]["has_next"] is False

    def test_all_parameters(self, mock_dependencies):
        """测试所有参数"""
        mock_dependencies.route.return_value = [{"field1": "value1"}]

        result = query_objects.invoke({
            "object_type": "测试对象",
            "select": ["field1"],
            "where": [{"field": "field2", "op": "eq", "value": "value2"}],
            "include_links": [{"relation": "rel1", "fields": ["field3"]}],
            "metrics": [{"field": "field4", "aggregation": "sum"}],
            "group_by": [{"field": "field5"}],
            "having": [{"field": "field6", "op": "gt", "value": 100}],
            "order_by": [{"field": "field7", "direction": "desc"}],
            "limit": 50,
            "offset": 10,
        })

        assert result["status"] == "success"

        # 验证所有参数都传递给了 router
        call_args = mock_dependencies.route.call_args[1]["oql_params"]
        assert call_args["object"] == "测试对象"
        assert call_args["fields"] == ["field1"]
        assert call_args["where"] is not None
        assert call_args["include_links"] is not None
        assert call_args["metrics"] is not None
        assert call_args["group_by"] is not None
        assert call_args["having"] is not None
        assert call_args["order_by"] is not None
        assert call_args["limit"] == 50
        assert call_args["offset"] == 10
