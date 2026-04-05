"""
OQL 原子翻译层和策略 A 测试
"""

import pytest
from datacloud_data_sdk.oql.adapter import (
    resolve_object, resolve_column, build_field_map, get_quoting,
    inline_value, expand_relative_date, translate_simple_condition,
    translate_logic_condition, translate_conditions, preprocess_where_terms,
    OqlAdapter
)
from datacloud_data_sdk.models import OQLError, OQLErrorCode
from tests.datacloud_data.fixtures.oql_test_data import (
    MockRegistry, MockTermResolver, TEST_FLIGHT_RECORDS
)


class TestResolveObject:
    """测试对象解析"""

    def test_resolve_object_success(self):
        """成功解析对象"""
        registry = MockRegistry()
        cls = resolve_object("Flight", registry)
        assert cls.object_code == "Flight"
        assert cls.source_type == "DB"

    def test_resolve_object_not_found(self):
        """对象不存在"""
        registry = MockRegistry()
        with pytest.raises(OQLError) as exc_info:
            resolve_object("NonExistent", registry)
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT


class TestResolveColumn:
    """测试字段解析（三级回退）"""

    def test_resolve_column_success(self):
        """成功解析字段"""
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        col = resolve_column("flight_id", cls, "MYSQL")
        assert col == "id"

    def test_resolve_column_not_found(self):
        """字段不存在"""
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        with pytest.raises(OQLError) as exc_info:
            resolve_column("nonexistent_field", cls, "MYSQL")
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNKNOWN_FIELD


class TestBuildFieldMap:
    """测试字段映射表构建"""

    def test_build_field_map(self):
        """构建字段映射表"""
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["flight_id", "flight_number"], "MYSQL")
        assert field_map["flight_id"] == "id"
        assert field_map["flight_number"] == "flight_no"


class TestGetQuoting:
    """测试 SQL 引号字符"""

    def test_mysql_quoting(self):
        assert get_quoting("MYSQL") == "`"

    def test_postgresql_quoting(self):
        assert get_quoting("POSTGRESQL") == '"'

    def test_hive_quoting(self):
        assert get_quoting("HIVE") == "`"


class TestInlineValue:
    """测试值内联"""

    def test_inline_null(self):
        assert inline_value(None) == "NULL"

    def test_inline_bool(self):
        assert inline_value(True) == "TRUE"
        assert inline_value(False) == "FALSE"

    def test_inline_number(self):
        assert inline_value(42) == "42"
        assert inline_value(3.14) == "3.14"

    def test_inline_string(self):
        assert inline_value("hello") == "'hello'"
        assert inline_value("it's") == "'it''s'"  # 转义单引号

    def test_inline_list(self):
        result = inline_value([1, 2, 3])
        assert "1" in result and "2" in result and "3" in result


class TestExpandRelativeDate:
    """测试相对日期展开"""

    def test_expand_today(self):
        start, end = expand_relative_date("today")
        assert start is not None
        assert end is not None
        assert start < end

    def test_expand_yesterday(self):
        start, end = expand_relative_date("yesterday")
        assert start is not None
        assert end is not None

    def test_expand_last_7_days(self):
        start, end = expand_relative_date("last_7_days")
        assert start is not None
        assert end is not None

    def test_expand_invalid(self):
        with pytest.raises(OQLError) as exc_info:
            expand_relative_date("invalid_expr")
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_INVALID_OPERATOR


class TestTranslateSimpleCondition:
    """测试简单条件翻译"""

    def test_eq_condition(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        sql = translate_simple_condition(
            {"field": "status", "op": "eq", "value": "completed"},
            field_map, "MYSQL", params, "`"
        )
        assert "=" in sql
        assert len(params) == 1

    def test_in_condition_empty(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        sql = translate_simple_condition(
            {"field": "status", "op": "in", "value": []},
            field_map, "MYSQL", params, "`"
        )
        assert sql == "1=0"

    def test_in_condition_values(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        sql = translate_simple_condition(
            {"field": "status", "op": "in", "value": ["completed", "pending"]},
            field_map, "MYSQL", params, "`"
        )
        assert "IN" in sql
        assert len(params) == 2

    def test_between_condition(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["departure_time"], "MYSQL")
        params = []

        sql = translate_simple_condition(
            {"field": "departure_time", "op": "between", "value": ["2024-01-01", "2024-01-31"]},
            field_map, "MYSQL", params, "`"
        )
        assert "BETWEEN" in sql
        assert len(params) == 2

    def test_invalid_operator(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        with pytest.raises(OQLError) as exc_info:
            translate_simple_condition(
                {"field": "status", "op": "invalid_op", "value": "test"},
                field_map, "MYSQL", params, "`"
            )
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_INVALID_OPERATOR


class TestTranslateConditions:
    """测试条件数组翻译"""

    def test_single_condition(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        sql = translate_conditions(
            [{"field": "status", "op": "eq", "value": "completed"}],
            field_map, "MYSQL", params, "`"
        )
        assert "=" in sql
        assert len(params) == 1

    def test_multiple_conditions(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status", "crew_id"], "MYSQL")
        params = []

        sql = translate_conditions(
            [
                {"field": "status", "op": "eq", "value": "completed"},
                {"field": "crew_id", "op": "eq", "value": "C001"},
            ],
            field_map, "MYSQL", params, "`"
        )
        assert "AND" in sql
        assert len(params) == 2


class TestOqlAdapter:
    """测试策略 A 执行器"""

    def test_translate_db_object(self):
        """翻译 DB 对象查询"""
        registry = MockRegistry()
        adapter = OqlAdapter()
        term_resolver = MockTermResolver()

        oql_params = {
            "object": "Flight",
            "fields": ["flight_id", "flight_number", "status"],
            "where": [{"field": "status", "op": "eq", "value": "completed"}],
            "limit": 10,
        }

        cls = registry.get_class("Flight")
        task = adapter.translate(oql_params, cls, "MYSQL", registry, term_resolver)

        assert task.datasource_alias == "mysql_main"
        assert "SELECT" in task.sql_template
        assert "WHERE" in task.sql_template

    def test_translate_api_object(self):
        """翻译 API 对象查询"""
        registry = MockRegistry()
        adapter = OqlAdapter()
        term_resolver = MockTermResolver()

        oql_params = {
            "object": "Manual",
            "fields": ["manual_id", "manual_name"],
            "where": [{"field": "manual_id", "op": "eq", "value": "M001"}],
        }

        cls = registry.get_class("Manual")
        task = adapter.translate(oql_params, cls, "API", registry, term_resolver)

        assert task.object_code == "Manual"
        assert task.params.get("manual_id") == "M001"


class TestTranslateConditions:
    """测试条件数组翻译"""

    def test_single_condition(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status"], "MYSQL")
        params = []

        sql = translate_conditions(
            [{"field": "status", "op": "eq", "value": "completed"}],
            field_map, "MYSQL", params, "`"
        )
        assert "=" in sql
        assert len(params) == 1

    def test_multiple_conditions(self):
        registry = MockRegistry()
        cls = registry.get_class("Flight")
        field_map = build_field_map(cls, ["status", "crew_id"], "MYSQL")
        params = []

        sql = translate_conditions(
            [
                {"field": "status", "op": "eq", "value": "completed"},
                {"field": "crew_id", "op": "eq", "value": "C001"},
            ],
            field_map, "MYSQL", params, "`"
        )
        assert "AND" in sql
        assert len(params) == 2
