"""QueryObjects 工具单元测试。

metrics 格式遵循 OQL 协议规范：{"name": "结果列名", "op": "操作符", "field": "属性名"}
group_by 时间粒度使用 granularity 字段：{"field": "属性名", "granularity": "week"}
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
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

    def test_aggregation_query_oql_spec_format(self, mock_dependencies):
        """测试聚合查询（OQL 协议格式：name/op/field）"""
        mock_dependencies.route.return_value = [
            {"部门": "技术部", "总薪资": 50000, "人数": 5},
            {"部门": "产品部", "总薪资": 40000, "人数": 4},
        ]

        # OQL 协议规范格式：{name, op, field}
        result = query_objects.invoke({
            "object_type": "员工",
            "metrics": [
                {"name": "总薪资", "op": "sum", "field": "薪资"},
                {"name": "人数", "op": "count"},
            ],
            "group_by": [{"field": "部门"}],
        })

        assert result["status"] == "success"
        assert result["result"]["columns"] == ["部门", "总薪资", "人数"]
        assert len(result["result"]["rows"]) == 2

    def test_aggregation_query_with_time_granularity(self, mock_dependencies):
        """测试聚合查询（时间粒度 granularity 字段）"""
        mock_dependencies.route.return_value = [
            {"航空公司": "CA", "起飞时间": "2026-W14", "航班总数": 120, "平均延误": 35.5},
        ]

        result = query_objects.invoke({
            "object_type": "航班",
            "where": [{"field": "状态", "op": "eq", "value": "延误"}],
            "metrics": [
                {"name": "航班总数", "op": "count"},
                {"name": "平均延误", "op": "avg", "field": "延误时长"},
            ],
            "group_by": [
                {"field": "航空公司"},
                {"field": "起飞时间", "granularity": "week"},
            ],
            "having": [{"field": "航班总数", "op": "gt", "value": 50}],
        })

        assert result["status"] == "success"
        call_args = mock_dependencies.route.call_args[1]["oql_params"]
        # 验证 granularity 字段传递给 router
        group_by = call_args["group_by"]
        time_dim = next(g for g in group_by if g["field"] == "起飞时间")
        assert time_dim["granularity"] == "week"

    def test_include_links(self, mock_dependencies):
        """测试关系漫游（OQL 协议 path 格式）"""
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
                {"path": "归属客户", "select": ["客户名称", "联系电话"]}
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
        """测试所有参数均正确传递给 router"""
        mock_dependencies.route.return_value = [{"field1": "value1"}]

        result = query_objects.invoke({
            "object_type": "测试对象",
            "select": ["field1"],
            "where": [{"field": "field2", "op": "eq", "value": "value2"}],
            "include_links": [{"path": "rel1", "select": ["field3"]}],
            "metrics": [{"name": "总计", "op": "sum", "field": "field4"}],
            "group_by": [{"field": "field5"}],
            "having": [{"field": "总计", "op": "gt", "value": 100}],
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

    def test_file_export_when_total_gte_limit(self, mock_dependencies, tmp_path):
        """当 total >= limit 时自动落文件，结果含 file_id。"""
        # 返回 100 条（等于 limit=100），触发落文件
        mock_dependencies.route.return_value = [
            {"合同号": f"C{i:04d}", "金额": i * 1000} for i in range(100)
        ]

        import os
        old_env = os.environ.get("DATACLOUD_WORKSPACE_DIR")
        os.environ["DATACLOUD_WORKSPACE_DIR"] = str(tmp_path)
        try:
            result = query_objects.invoke({
                "object_type": "合同",
                "limit": 100,
            })
        finally:
            if old_env is None:
                os.environ.pop("DATACLOUD_WORKSPACE_DIR", None)
            else:
                os.environ["DATACLOUD_WORKSPACE_DIR"] = old_env

        assert result["status"] == "success"
        assert "file_id" in result["result"]
        # 文件应写入 tmp_path/exports/
        exports_dir = tmp_path / "exports"
        assert exports_dir.exists()
        file_id = result["result"]["file_id"]
        assert (exports_dir / f"{file_id}.json").exists()
        assert (exports_dir / f"{file_id}_meta.json").exists()

    def test_no_file_export_when_total_lt_limit(self, mock_dependencies, tmp_path):
        """total < limit 时不落文件，结果不含 file_id。"""
        mock_dependencies.route.return_value = [
            {"id": i} for i in range(5)
        ]

        import os
        os.environ["DATACLOUD_WORKSPACE_DIR"] = str(tmp_path)
        try:
            result = query_objects.invoke({
                "object_type": "测试",
                "limit": 100,
            })
        finally:
            os.environ.pop("DATACLOUD_WORKSPACE_DIR", None)

        assert result["status"] == "success"
        assert "file_id" not in result["result"]

    def test_relative_date_filter(self, mock_dependencies):
        """测试 relativeDate 操作符传递"""
        mock_dependencies.route.return_value = [{"航班号": "CA123", "延误时长": 45}]

        result = query_objects.invoke({
            "object_type": "航班",
            "where": [
                {"field": "起飞时间", "op": "relativeDate", "value": "this_month"},
                {"field": "状态", "op": "in", "value": ["延误", "取消"]},
            ],
            "order_by": [{"field": "延误时长", "direction": "desc"}],
        })

        assert result["status"] == "success"
        call_args = mock_dependencies.route.call_args[1]["oql_params"]
        where = call_args["where"]
        date_cond = next(c for c in where if c.get("op") == "relativeDate")
        assert date_cond["value"] == "this_month"
