"""DynamicQueryToolGenerator 单元测试。"""

from datacloud_data.ontology.loader import OntologyLoader
from datacloud_data.ontology.term_loader import TermLoader

from datacloud_data_service.tools.dynamic_query_tool_generator import (
    DynamicQueryToolGenerator,
)


def test_db_object_generates_query_tool_with_filters_aggregates() -> None:
    """DB 对象生成 query_{object_code}，含 filters、aggregates、group_by。"""
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    gen = DynamicQueryToolGenerator(loader)
    tool = gen.generate("sales_business_opportunity")
    assert tool is not None
    assert tool["name"] == "query_sales_business_opportunity"
    schema = tool["inputSchema"]["properties"]
    assert "filters" in schema
    assert "aggregates" in schema
    agg_items = schema["aggregates"]["items"]
    assert "as" in agg_items["properties"]
    assert "as" not in agg_items.get("required", [])
    assert "模型" in agg_items["properties"]["as"].get("description", "")
    assert "group_by" in schema
    assert tool["_meta"]["source_type"] == "DB"


def test_kb_object_generates_query_tool_with_query_and_filters() -> None:
    """KB 对象生成 query_{object_code}，含 query、filters，无 aggregates。"""
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    gen = DynamicQueryToolGenerator(loader)
    tool = gen.generate("sales_daily_report")
    assert tool is not None
    assert tool["name"] == "query_sales_daily_report"
    schema = tool["inputSchema"]["properties"]
    assert "query" in schema
    assert "filters" in schema
    assert "aggregates" not in schema
    assert tool["_meta"]["source_type"] == "KNOWLEDGE_BASE"


def test_api_object_returns_none() -> None:
    """API 对象不生成虚拟动作。"""
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    gen = DynamicQueryToolGenerator(loader)
    tool = gen.generate("po_users")
    assert tool is None


def test_db_filters_use_object_schema_with_per_field_properties() -> None:
    """DB 对象 filters 为 object，每字段独立 schema，含 is_null/is_not_null。"""
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    gen = DynamicQueryToolGenerator(loader)
    tool = gen.generate("sales_business_opportunity")
    assert tool is not None
    filters = tool["inputSchema"]["properties"]["filters"]
    assert filters["type"] == "object"
    assert "properties" in filters
    assert filters.get("additionalProperties") is False
    # 检查某字段有独立 schema
    bo_name = filters["properties"].get("boName", {})
    assert bo_name.get("type") == "object"
    assert "description" in bo_name
    assert "主键ID" in str(filters["properties"].get("id", {}).get("description", "")) or "商机名称" in str(bo_name.get("description", ""))
    ops = bo_name.get("properties", {}).get("op", {}).get("enum", [])
    assert "is_null" in ops
    assert "is_not_null" in ops
    assert "like" in ops


def test_term_field_gets_enum_when_term_loader_configured() -> None:
    """配置 term_loader 时，术语字段的 value 有 enum。"""
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    term_loader = TermLoader.from_mapping(
        {"staffName.code": [{"code": "E001", "label": "张三"}, {"code": "E002", "label": "李四"}]}
    )
    loader.configure(term_loader=term_loader)
    gen = DynamicQueryToolGenerator(loader)
    # po_users_kpi_summary 有 empNo 绑定 staffName.code
    tool = gen.generate("po_users_kpi_summary")
    assert tool is not None
    filters = tool["inputSchema"]["properties"]["filters"]
    emp_no = filters["properties"].get("empNo", {})
    value_schema = emp_no.get("properties", {}).get("value", {})
    assert value_schema.get("type") == "string"
    assert "enum" in value_schema
    assert value_schema["enum"] == ["E001", "E002"]
