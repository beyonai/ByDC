from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.object_view_builder import ObjectViewBuilder

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_business_opportunity",
            "fields": [
                {
                    "field_code": "bo_id",
                    "field_name": "商机ID",
                    "field_type": "STRING",
                }
            ],
            "actions": [],
        },
        {
            "object_code": "sales_contract",
            "object_name": "销售合同",
            "description": "合同对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_contract",
            "fields": [
                {
                    "field_code": "contract_id",
                    "field_name": "合同ID",
                    "field_type": "STRING",
                }
            ],
            "actions": [],
        },
    ],
    "relations": [
        {
            "relation_code": "bo_to_contract",
            "source_class": "sales_bo",
            "target_class": "sales_contract",
            "relation_type": "ONE_TO_MANY",
            "join_keys": [{"from_field": "bo_id", "to_field": "bo_id"}],
            "description": "一个商机可以签署多份合同",
        }
    ],
}


def test_build_object_view_has_sources_and_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo", "sales_contract"], view_id="test_view")
    assert len(payload.objects) == 2
    assert len(payload.sources) >= 1


def test_build_object_view_has_relations_with_description() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo", "sales_contract"], view_id="test_view")
    assert len(payload.relations) == 1
    assert "合同" in payload.relations[0].description


def test_object_view_object_has_name_and_description() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo"], view_id="test_view")
    assert payload.objects[0].object_name == "销售商机"
