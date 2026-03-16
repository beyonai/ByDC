from datacloud_data.ontology.loader import OntologyLoader

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
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
                },
            ],
            "actions": [],
        },
    ],
    "relations": [
        {
            "relation_code": "bo_to_contract",
            "relation_name": "商机关联合同",
            "source_class": "sales_bo",
            "target_class": "sales_contract",
            "relation_type": "ONE_TO_MANY",
            "join_keys": [{"from_field": "bo_id", "to_field": "bo_id"}],
            "description": "一个商机可签署多份合同",
        }
    ],
}

SCENE = {
    "view_id": "scene_01",
    "view_name": "CRM销售分析视图",
    "description": "包含商机与合同",
    "object_ids": ["sales_bo", "sales_contract"],
}


def test_view_get_description_contains_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")
    desc = view.get_description()
    assert "销售商机" in desc
    assert "销售合同" in desc
    assert "一个商机可签署多份合同" in desc or "sales_contract" in desc


def test_view_list_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")
    assert len(view.objects) == 2
