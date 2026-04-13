from datacloud_data_sdk.ontology.loader import OntologyLoader

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


def test_build_view_result_columns_meta_uses_property_name() -> None:
    """视图 meta.columns 应带 label，供 Markdown 等展示中文列名。"""
    from types import SimpleNamespace

    from datacloud_data_sdk.executor.view_executor_support import build_view_result_columns_meta
    from datacloud_data_sdk.virtual_action.models import ViewFieldMeta

    vf = ViewFieldMeta(
        property_code="phy_grid_id",
        property_name="物理网格编码",
        source_object_code="o1",
        source_object_column_code="c1",
        field_type="STRING",
    )
    view = SimpleNamespace(fields=[vf])
    cols = build_view_result_columns_meta(view, ["phy_grid_id", "missing_col"])
    assert cols[0]["name"] == "phy_grid_id"
    assert cols[0]["label"] == "物理网格编码"
    assert cols[1]["name"] == "missing_col"
    assert cols[1]["label"] == "missing_col"
