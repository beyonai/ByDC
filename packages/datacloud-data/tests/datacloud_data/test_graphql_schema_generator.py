"""GraphQL Schema 从本体（OntologyClass 列表）生成的测试。"""

from datacloud_data_sdk.graphql.schema_generator import generate_schema
from datacloud_data_sdk.ontology.models import OntologyClass, OntologyField


def test_generate_schema_from_ontology_class_basic() -> None:
    """从 OntologyClass 列表生成 GraphQL schema，含对应类型与字段。"""
    classes = [
        OntologyClass(
            object_code="customer",
            object_name="客户",
            description="客户对象",
            source_type="DB",
            fields=[
                OntologyField(field_code="id", field_name="ID", field_type="STRING"),
                OntologyField(field_code="name", field_name="名称", field_type="STRING"),
                OntologyField(field_code="age", field_name="年龄", field_type="INTEGER"),
            ],
        ),
    ]
    schema = generate_schema(classes, [])
    assert "type Customer" in schema
    assert "id: String" in schema
    assert "name: String" in schema
    assert "age: Int" in schema


def test_generate_schema_field_type_mapping() -> None:
    """field_type 正确映射到 GraphQL 标量。"""
    classes = [
        OntologyClass(
            object_code="product",
            object_name="产品",
            description="",
            source_type="DB",
            fields=[
                OntologyField(field_code="title", field_name="标题", field_type="STRING"),
                OntologyField(field_code="price", field_name="价格", field_type="NUMBER"),
                OntologyField(field_code="count", field_name="数量", field_type="INTEGER"),
                OntologyField(field_code="active", field_name="启用", field_type="BOOLEAN"),
                OntologyField(field_code="created_at", field_name="创建时间", field_type="DATE"),
            ],
        ),
    ]
    schema = generate_schema(classes, [])
    assert "type Product" in schema
    assert "title: String" in schema
    assert "price: Float" in schema
    assert "count: Int" in schema
    assert "active: Boolean" in schema
    assert "created_at: String" in schema


def test_generate_schema_multiple_classes() -> None:
    """多个 OntologyClass 生成多个 GraphQL 类型。"""
    classes = [
        OntologyClass(
            object_code="customer",
            object_name="客户",
            description="",
            source_type="DB",
            fields=[OntologyField(field_code="id", field_name="ID", field_type="STRING")],
        ),
        OntologyClass(
            object_code="opportunity",
            object_name="商机",
            description="",
            source_type="DB",
            fields=[OntologyField(field_code="id", field_name="ID", field_type="STRING")],
        ),
    ]
    schema = generate_schema(classes, [])
    assert "type Customer" in schema
    assert "type Opportunity" in schema
