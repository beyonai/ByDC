from datacloud_data_sdk.ontology.models import (
    FieldPhysicalMapping,
    OntologyField,
    OntologyActionParam,
    OntologyAction,
    OntologyRelation,
    OntologyClass,
)


def test_ontology_field_has_term_type_and_dataset_id() -> None:
    f = OntologyField(
        field_code="x",
        field_name="X",
        field_type="STRING",
        term_set="user.code",
        term_type="enum",
        dataset_id=12,
    )
    assert f.term_type == "enum"
    assert f.dataset_id == 12


def test_field_has_term_set_and_source_column() -> None:
    f = OntologyField(
        field_code="stage_code",
        field_name="商机阶段",
        field_type="STRING",
        term_set="bo_stage",
        source_column="stage_code",
    )
    assert f.term_set == "bo_stage"
    assert f.source_column == "stage_code"


def test_ontology_class_has_datasource_alias() -> None:
    cls = OntologyClass(
        object_code="sales_bo",
        object_name="销售商机",
        description="商机对象",
        source_type="DB",
        datasource_alias="crm_db",
        table_name="sales_business_opportunity",
    )
    assert cls.datasource_alias == "crm_db"
    assert cls.source_type == "DB"


def test_ontology_action_has_script_field() -> None:
    action = OntologyAction(
        action_code="calc_score",
        action_name="计算评分",
        description="",
        belong_class="sales_bo",
        params=[],
        function_refs=[],
        action_type="operation",
        script="def execute(params):\n    return {'score': 100}",
    )
    assert action.script is not None
    assert "def execute" in action.script


def test_ontology_action_script_defaults_to_none() -> None:
    action = OntologyAction(
        action_code="query_bo",
        action_name="查商机",
        description="",
        belong_class="sales_bo",
        params=[],
        function_refs=["fn_get_bo"],
        action_type="query",
    )
    assert action.script is None


def test_ontology_relation_has_join_keys() -> None:
    rel = OntologyRelation(
        relation_code="bo_to_contract",
        relation_name="商机关联合同",
        source_class="sales_bo",
        target_class="sales_contract",
        relation_type="ONE_TO_MANY",
        join_keys=[{"from_field": "bo_id", "to_field": "bo_id"}],
        description="一个商机可签署多份合同",
    )
    assert rel.join_keys[0]["from_field"] == "bo_id"


def test_ontology_field_has_property_kind_and_derived_config() -> None:
    from datacloud_data_sdk.ontology.models import OntologyField

    f = OntologyField(
        field_code="discount_amount",
        field_name="折后金额",
        field_type="NUMBER",
        property_kind="derived",
        derived_config={
            "mode": "expression",
            "expression": "amount * 0.9",
            "depends_on": ["amount"],
        },
    )
    assert f.property_kind == "derived"
    assert f.derived_config["mode"] == "expression"


def test_ontology_relation_has_resolve_action() -> None:
    from datacloud_data_sdk.ontology.models import OntologyRelation

    r = OntologyRelation(
        relation_code="cust_opp",
        source_class="customer",
        target_class="opportunity",
        relation_type="ONE_TO_MANY",
        resolve_action_code="query_opp_by_cust",
        resolve_param_binding={"source_field": "customer_id", "action_param": "customerId"},
    )
    assert r.resolve_action_code == "query_opp_by_cust"
    assert r.resolve_param_binding["source_field"] == "customer_id"
