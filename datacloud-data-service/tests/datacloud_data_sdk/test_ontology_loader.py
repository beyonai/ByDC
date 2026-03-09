import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.exceptions import ObjectNotFoundError

MINIMAL_REGISTRY = {
    "functions": [
        {
            "function_code": "fn_get_emp",
            "function_type": "API",
            "api_schema": {
                "servers": [{"url": "http://mock:8080"}],
                "paths": {"/api/v1/emp": {"post": {}}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_emp",
            "object_name": "员工",
            "description": "销售员工",
            "source_type": "API",
            "fields": [
                {"field_code": "emp_id", "field_name": "员工ID", "field_type": "STRING"}
            ],
            "actions": [
                {
                    "action_code": "query_emp",
                    "action_name": "查员工",
                    "description": "",
                    "params": [],
                    "function_refs": ["fn_get_emp"],
                }
            ],
        }
    ],
    "relations": [],
}

REGISTRY_WITH_SCRIPT = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"}
            ],
            "actions": [
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "description": "计算商机评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "params": [
                        {
                            "param_code": "bo_id",
                            "param_name": "商机ID",
                            "direction": "IN",
                            "param_type": "STRING",
                            "required": True,
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
        }
    ],
    "relations": [],
}


def test_load_from_content_parses_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cls = loader.get_ontology_class("sales_emp")
    assert cls.object_code == "sales_emp"
    assert len(cls.fields) == 1


def test_get_unknown_object_raises() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    with pytest.raises(ObjectNotFoundError):
        loader.get_ontology_class("nonexistent")


def test_get_function_config_returns_api_schema() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cfg = loader.get_function_config("fn_get_emp")
    assert "servers" in cfg


def test_action_script_parsed_correctly() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY_WITH_SCRIPT)
    cls = loader.get_ontology_class("sales_bo")
    action = cls.actions[0]
    assert action.script is not None
    assert "def execute" in action.script
    assert action.action_code == "calc_score"


def test_action_without_script_has_none() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cls = loader.get_ontology_class("sales_emp")
    assert cls.actions[0].script is None


def test_configure_sets_plan_generator() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    loader.configure(csv_base_dir="/tmp/test")
    assert loader._config.csv_base_dir == "/tmp/test"


def test_configure_sql_execution_mode():
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    loader = OntologyLoader()
    loader.configure(sql_execution_mode="external")
    assert loader._config.sql_execution_mode == "external"
