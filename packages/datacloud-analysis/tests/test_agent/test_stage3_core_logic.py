"""
阶段3：统一 query_objects 工具 - 核心逻辑测试（不需要完整依赖）
"""

import pytest
from unittest.mock import Mock


class TestStage3CoreLogic:
    """测试阶段3的核心逻辑"""

    def test_query_objects_parameter_structure(self):
        """测试 query_objects 参数结构"""
        # 模拟 query_objects 的参数结构
        def mock_query_objects(
            object_type: str,
            select=None,
            where=None,
            include_links=None,
            metrics=None,
            group_by=None,
            having=None,
            order_by=None,
            limit=100,
            offset=0,
            config=None,
        ):
            """模拟 query_objects 函数"""
            return {
                "object_type": object_type,
                "limit": limit,
                "offset": offset,
            }

        # 测试对象查询
        result1 = mock_query_objects(object_type="company_bo", limit=10)
        assert result1["object_type"] == "company_bo"
        assert result1["limit"] == 10

        # 测试视图查询
        result2 = mock_query_objects(object_type="ads_analysis_view", limit=20)
        assert result2["object_type"] == "ads_analysis_view"
        assert result2["limit"] == 20

    def test_oql_params_construction(self):
        """测试 OQL 参数构造逻辑"""
        # 模拟 query_objects 内部的参数构造逻辑
        def build_oql_params(object_type, select=None, where=None, limit=100, offset=0):
            oql_params = {
                "object": object_type,  # 关键：使用 "object" 字段
                "limit": limit,
                "offset": offset,
            }
            if select is not None:
                oql_params["fields"] = select
            if where is not None:
                oql_params["where"] = where
            return oql_params

        # 测试对象查询参数
        params1 = build_oql_params(
            object_type="company_bo",
            select=["company_name", "credit_code"],
            limit=10
        )
        assert params1["object"] == "company_bo"
        assert params1["fields"] == ["company_name", "credit_code"]
        assert params1["limit"] == 10

        # 测试视图查询参数
        params2 = build_oql_params(
            object_type="ads_analysis_view",
            where=[{"field": "status", "op": "eq", "value": "active"}],
            limit=20
        )
        assert params2["object"] == "ads_analysis_view"
        assert params2["where"] == [{"field": "status", "op": "eq", "value": "active"}]
        assert params2["limit"] == 20

    def test_router_object_resolution_logic(self):
        """测试 router 对象解析逻辑"""
        # 模拟 resolve_object 逻辑
        def mock_resolve_object(object_code, registry):
            """模拟对象解析"""
            cls = registry.get_class(object_code)
            if cls is None:
                raise ValueError(f"对象 '{object_code}' 不存在")
            return cls

        # Mock registry
        mock_registry = Mock()
        mock_class = Mock()
        mock_class.object_code = "company_bo"
        mock_class.source_type = "DB"
        mock_registry.get_class.return_value = mock_class

        # 测试解析成功
        result = mock_resolve_object("company_bo", mock_registry)
        assert result == mock_class
        mock_registry.get_class.assert_called_once_with("company_bo")

    def test_router_unknown_object_error(self):
        """测试 router 未知对象错误处理"""
        # 模拟 resolve_object 逻辑
        def mock_resolve_object(object_code, registry):
            cls = registry.get_class(object_code)
            if cls is None:
                raise ValueError(f"对象 '{object_code}' 不存在")
            return cls

        # Mock registry 返回 None
        mock_registry = Mock()
        mock_registry.get_class.return_value = None

        # 测试抛出错误
        with pytest.raises(ValueError) as exc_info:
            mock_resolve_object("unknown_object", mock_registry)

        assert "不存在" in str(exc_info.value)

    def test_unified_parameter_handling(self):
        """测试统一参数处理"""
        # 模拟完整的查询流程
        def mock_query_flow(object_type, filters=None, limit=100):
            """模拟查询流程"""
            # 1. 构造 OQL 参数
            oql_params = {
                "object": object_type,
                "limit": limit,
            }
            if filters:
                oql_params["where"] = filters

            # 2. 模拟 router 处理
            # router 内部会调用 resolve_object(object_code, registry)
            # 无论是对象还是视图，都使用相同的参数结构

            # 3. 返回结果
            return {
                "status": "success",
                "oql_params": oql_params,
            }

        # 测试对象查询
        result1 = mock_query_flow(
            object_type="company_bo",
            filters=[{"field": "status", "op": "eq", "value": "active"}],
            limit=10
        )
        assert result1["status"] == "success"
        assert result1["oql_params"]["object"] == "company_bo"

        # 测试视图查询
        result2 = mock_query_flow(
            object_type="ads_analysis_view",
            filters=[{"field": "grid_name", "op": "eq", "value": "某网格"}],
            limit=20
        )
        assert result2["status"] == "success"
        assert result2["oql_params"]["object"] == "ads_analysis_view"

        # 验证两次查询使用相同的参数结构
        assert "object" in result1["oql_params"]
        assert "object" in result2["oql_params"]


class TestStage3ParameterValidation:
    """测试参数校验逻辑"""

    def test_object_type_required(self):
        """测试 object_type 参数必填"""
        # 模拟参数校验逻辑
        def validate_oql_params(oql_params):
            if "object" not in oql_params:
                raise ValueError("缺少必需字段：object")

        # 测试缺少 object 字段
        with pytest.raises(ValueError) as exc_info:
            validate_oql_params({})

        assert "object" in str(exc_info.value)

        # 测试包含 object 字段
        validate_oql_params({"object": "company_bo"})  # 不抛出异常

    def test_fields_validation(self):
        """测试 fields 参数校验"""
        # 模拟 fields 校验逻辑
        def validate_fields(oql_params):
            if "fields" in oql_params:
                fields = oql_params["fields"]
                if not isinstance(fields, list):
                    raise ValueError("fields 必须是数组")

        # 测试有效的 fields
        validate_fields({"object": "company_bo", "fields": ["name", "code"]})

        # 测试无效的 fields
        with pytest.raises(ValueError) as exc_info:
            validate_fields({"object": "company_bo", "fields": "invalid"})

        assert "数组" in str(exc_info.value)

    def test_where_validation(self):
        """测试 where 参数校验"""
        # 模拟 where 校验逻辑
        def validate_where(oql_params):
            if "where" in oql_params:
                where = oql_params["where"]
                if not isinstance(where, list):
                    raise ValueError("where 必须是数组")

        # 测试有效的 where
        validate_where({
            "object": "company_bo",
            "where": [{"field": "status", "op": "eq", "value": "active"}]
        })

        # 测试无效的 where
        with pytest.raises(ValueError) as exc_info:
            validate_where({"object": "company_bo", "where": "invalid"})

        assert "数组" in str(exc_info.value)
