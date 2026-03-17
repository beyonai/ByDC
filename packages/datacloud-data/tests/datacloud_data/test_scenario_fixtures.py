"""测试 scenario 本体 fixtures 加载与数据初始化。"""

import pytest

from datacloud_data.executor.dynamic_query_executor import DynamicQueryExecutor
from datacloud_data.ontology.loader import OntologyLoader


def test_load_scenario_db_linked(load_scenario_db_linked: OntologyLoader) -> None:
    """load_scenario_db_linked 能正确加载 scenario_db_linked.json。"""
    loader = load_scenario_db_linked
    cust = loader.get_ontology_class("customer")
    opp = loader.get_ontology_class("opportunity")
    assert cust.source_type == "DB"
    assert cust.table_name == "customer"
    assert opp.table_name == "opportunity"
    opportunities_field = next(f for f in cust.fields if f.field_code == "opportunities")
    assert opportunities_field.property_kind == "linked"
    assert opportunities_field.relation_ref == "customer_has_opportunities"
    rels = loader.get_ontology_relations()
    assert len(rels) == 1
    assert rels[0].relation_code == "customer_has_opportunities"
    assert rels[0].join_keys[0]["from_field"] == "customer_id"
    assert rels[0].join_keys[0]["to_field"] == "customer_id"


@pytest.mark.asyncio
async def test_scenario_db_linked_with_data(scenario_db_linked_with_data) -> None:
    """scenario_db_linked_with_data 创建表并插入数据后，能正确查询。"""
    loader, ds_manager = scenario_db_linked_with_data
    executor = DynamicQueryExecutor(loader, ds_manager=ds_manager)
    result = await executor.execute("customer", {"filters": {}})
    assert result["total"] == 2
    assert len(result["records"]) == 2
    names = [r["name"] for r in result["records"]]
    assert "c1" in names and "c2" in names
    opp_result = await executor.execute("opportunity", {"filters": {}})
    assert opp_result["total"] == 3


@pytest.mark.asyncio
async def test_scenario_db_linked_opportunities_nested(scenario_db_linked_with_data) -> None:
    """customer 查询返回 opportunities 嵌套列表，c1 有 2 条，c2 有 1 条。"""
    loader, ds_manager = scenario_db_linked_with_data
    executor = DynamicQueryExecutor(loader, ds_manager=ds_manager)
    result = await executor.execute("customer", {"filters": {}})
    assert result["total"] == 2
    assert "opportunities" in result["records"][0]
    by_name = {r["name"]: r for r in result["records"]}
    assert len(by_name["c1"]["opportunities"]) == 2
    assert len(by_name["c2"]["opportunities"]) == 1
    # 验证嵌套结构：opportunities 为 list[dict]，含 id、amount
    c1_opps = by_name["c1"]["opportunities"]
    assert all("id" in o and "amount" in o for o in c1_opps)
    amounts = [o["amount"] for o in c1_opps]
    assert 100 in amounts and 200 in amounts


def test_load_scenario_db_derived(load_scenario_db_derived: OntologyLoader) -> None:
    """load_scenario_db_derived 能正确加载 scenario_db_derived.json。"""
    loader = load_scenario_db_derived
    sales_bo = loader.get_ontology_class("sales_bo")
    customer = loader.get_ontology_class("customer")
    assert sales_bo.source_type == "DB"
    assert sales_bo.table_name == "sales_bo"
    discount_field = next(f for f in sales_bo.fields if f.field_code == "discount_amount")
    assert discount_field.property_kind == "derived"
    assert discount_field.derived_config.get("mode") == "expression"
    assert discount_field.derived_config.get("expression") == "amount * 0.9"
    opp_count_field = next(f for f in customer.fields if f.field_code == "opportunity_count")
    assert opp_count_field.property_kind == "derived"
    assert opp_count_field.derived_config.get("mode") == "aggregation"
    assert opp_count_field.derived_config.get("relation_ref") == "customer_has_opportunities"


@pytest.mark.asyncio
async def test_execute_db_derived_expression(scenario_db_derived_with_data) -> None:
    """derived expression 字段：discount_amount = amount * 0.9。"""
    loader, ds_manager = scenario_db_derived_with_data
    executor = DynamicQueryExecutor(loader, ds_manager=ds_manager)
    result = await executor.execute("sales_bo", {"filters": {}})
    assert result["total"] == 2
    assert "discount_amount" in result["records"][0]
    assert result["records"][0]["amount"] == 100
    assert result["records"][0]["discount_amount"] == 90.0  # 100 * 0.9
    assert result["records"][1]["amount"] == 200
    assert result["records"][1]["discount_amount"] == 180.0  # 200 * 0.9


@pytest.mark.asyncio
async def test_execute_db_derived_aggregation(scenario_db_derived_with_data) -> None:
    """derived aggregation 字段：opportunity_count，c1=2，c2=1。"""
    loader, ds_manager = scenario_db_derived_with_data
    executor = DynamicQueryExecutor(loader, ds_manager=ds_manager)
    result = await executor.execute("customer", {"filters": {}})
    assert result["total"] == 2
    assert "opportunity_count" in result["records"][0]
    by_name = {r["name"]: r for r in result["records"]}
    assert by_name["c1"]["opportunity_count"] == 2
    assert by_name["c2"]["opportunity_count"] == 1
