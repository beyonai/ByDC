import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import ActionNotFoundError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

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
            "actions": [
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "description": "计算商机评分",
                    "script": (
                        "def execute(params):\n"
                        "    owner_id = params.get('owner_id', '')\n"
                        "    return {'score': 100, 'owner_id': owner_id}\n"
                    ),
                    "function_refs": [],
                    "action_type": "operation",
                    "params": [
                        {
                            "param_code": "owner_id",
                            "param_name": "负责人ID",
                            "direction": "IN",
                            "param_type": "STRING",
                            "required": False,
                        },
                        {
                            "param_code": "score",
                            "param_name": "评分",
                            "direction": "OUT",
                            "param_type": "NUMBER",
                        },
                    ],
                }
            ],
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


def test_view_get_objects_returns_view_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")

    objects = view.get_objects()

    assert [obj.object_code for obj in objects] == ["sales_bo", "sales_contract"]


def test_view_get_object_returns_target_object() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")

    obj = view.get_object("sales_bo")

    assert obj.object_code == "sales_bo"
    assert "calc_score" in obj.list_action_codes()


@pytest.mark.asyncio
async def test_view_get_object_can_execute_object_action() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")

    with InvocationContext(session_id="view-object-action-confirm"):
        first = await view.get_object("sales_bo").invoke_action(
            "calc_score",
            {"owner_id": "u_001", "userConfirmed": False},
        )
        result = await view.get_object("sales_bo").invoke_action(
            "calc_score",
            {"owner_id": "u_001", "userConfirmed": True},
        )

    assert first["result_type"] == "ask_user"
    assert result["records"] == [{"score": 100, "owner_id": "u_001"}]
    assert result["meta"]["columns"] == ["score", "owner_id"]
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_view_invoke_action_only_supports_view_actions() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")

    with pytest.raises(ActionNotFoundError):
        await view.invoke_action("calc_score", {"owner_id": "u_001"})


def test_view_virtual_actions_refresh_after_late_injection() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "ads_grid_analysis",
                    "object_name": "物理网格综合分析表",
                    "source_type": "DB",
                    "table_name": "ads_grid_analysis",
                    "fields": [
                        {
                            "field_code": "grid_name",
                            "field_name": "物理网格名称",
                            "field_type": "STRING",
                            "ext_property": (
                                '{"property_role_rule": {"property_role": "DIMENSION", '
                                '"rule_type": "attribute_name"}}'
                            ),
                        },
                        {
                            "field_code": "total_revenue",
                            "field_name": "物理网格总营收（万元）",
                            "field_type": "DOUBLE",
                            "ext_property": (
                                '{"property_role_rule": {"property_role": "MEASURE", '
                                '"rule_type": "index_numerical"}}'
                            ),
                        },
                    ],
                    "actions": [],
                }
            ],
            "relations": [],
            "views": [
                {
                    "view_id": "scene_grid_analysis",
                    "view_name": "物理网格综合分析视图",
                    "description": "",
                    "objects": [{"object_code": "ads_grid_analysis"}],
                    "relations": [],
                    "mappings": [
                        {
                            "property_code": "grid_name",
                            "property_name": "物理网格名称",
                            "source_object_code": "ads_grid_analysis",
                            "source_object_column_code": "grid_name",
                            "ext_property": (
                                "{&quot;property_role_rule&quot;: "
                                "{&quot;property_role&quot;: &quot;DIMENSION&quot;, "
                                "&quot;rule_type&quot;: &quot;attribute_name&quot;}}"
                            ),
                        },
                        {
                            "property_code": "total_revenue",
                            "property_name": "物理网格总营收（万元）",
                            "source_object_code": "ads_grid_analysis",
                            "source_object_column_code": "total_revenue",
                            "ext_property": (
                                "{&quot;property_role_rule&quot;: "
                                "{&quot;property_role&quot;: &quot;MEASURE&quot;, "
                                "&quot;rule_type&quot;: &quot;index_numerical&quot;}}"
                            ),
                        },
                    ],
                }
            ],
        }
    )
    view = loader.get_view("scene_grid_analysis")

    assert view.list_action_codes() == []

    inject_virtual_actions(loader)

    assert "query_scene_grid_analysis" in view.list_action_codes()
    assert "compute_scene_grid_analysis" in view.list_action_codes()
    assert (
        view.get_action_schema("query_scene_grid_analysis")["name"] == "query_scene_grid_analysis"
    )


def test_view_compute_schema_supports_current_owl_role_and_kind_aliases() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "ads_enterprise_analysis",
                    "object_name": "企业分析表",
                    "source_type": "DB",
                    "table_name": "ads_enterprise_analysis",
                    "fields": [
                        {
                            "field_code": "enterprise_name",
                            "field_name": "企业名称",
                            "field_type": "STRING",
                            "ext_property": (
                                '{"property_role_rule": {"property_role": "DIMENSION", '
                                '"rule_type": "name"}}'
                            ),
                        },
                        {
                            "field_code": "total_revenue",
                            "field_name": "企业总营收（万元）",
                            "field_type": "DOUBLE",
                            "ext_property": (
                                '{"property_role_rule": {"property_role": "MEASURE", '
                                '"rule_type": "basic_metric"}}'
                            ),
                        },
                        {
                            "field_code": "grid_total_revenue",
                            "field_name": "所属网格总营收（万元）",
                            "field_type": "DOUBLE",
                            "ext_property": (
                                '{"property_role_rule": {"property_role": "DIMENSION", '
                                '"rule_type": "numeric"}}'
                            ),
                        },
                    ],
                    "actions": [],
                }
            ],
            "relations": [],
            "views": [
                {
                    "view_id": "scene_enterprise_analysis",
                    "view_name": "企业综合分析视图",
                    "description": "",
                    "objects": [{"object_code": "ads_enterprise_analysis"}],
                    "relations": [],
                    "mappings": [
                        {
                            "property_code": "enterprise_name",
                            "property_name": "企业名称",
                            "source_object_code": "ads_enterprise_analysis",
                            "source_object_column_code": "enterprise_name",
                            "ext_property": (
                                "{&quot;property_role_rule&quot;: "
                                "{&quot;property_role&quot;: &quot;DIMENSION&quot;, "
                                "&quot;rule_type&quot;: &quot;name&quot;}}"
                            ),
                        },
                        {
                            "property_code": "total_revenue",
                            "property_name": "企业总营收（万元）",
                            "source_object_code": "ads_enterprise_analysis",
                            "source_object_column_code": "total_revenue",
                            "ext_property": (
                                "{&quot;property_role_rule&quot;: "
                                "{&quot;property_role&quot;: &quot;MEASURE&quot;, "
                                "&quot;rule_type&quot;: &quot;basic_metric&quot;}}"
                            ),
                        },
                        {
                            "property_code": "grid_total_revenue",
                            "property_name": "所属网格总营收（万元）",
                            "source_object_code": "ads_enterprise_analysis",
                            "source_object_column_code": "grid_total_revenue",
                            "ext_property": (
                                "{&quot;property_role_rule&quot;: "
                                "{&quot;property_role&quot;: &quot;DIMENSION&quot;, "
                                "&quot;rule_type&quot;: &quot;numeric&quot;}}"
                            ),
                        },
                    ],
                }
            ],
        }
    )

    inject_virtual_actions(loader)

    view = loader.get_view("scene_enterprise_analysis")
    schema = view.get_action_schema("compute_scene_enterprise_analysis")["inputSchema"]
    measure_fields = schema["properties"]["metrics"]["x-dc-measure-fields"]
    measure_codes = {item["field"] for item in measure_fields}

    assert "total_revenue" in measure_codes
    assert "grid_total_revenue" in measure_codes


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
