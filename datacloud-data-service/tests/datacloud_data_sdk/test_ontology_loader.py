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


def test_ontology_class_parses_source_config() -> None:
    """对象含 source_config 时，OntologyClass 能解析并存储。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "test_obj",
                "object_name": "测试对象",
                "source_type": "DB",
                "table_name": "test_table",
                "source_config": {
                    "alias": "ds_test",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/test",
                },
                "fields": [],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    cls = loader.get_ontology_class("test_obj")
    assert cls.source_config is not None
    assert cls.source_config.get("alias") == "ds_test"
    assert cls.datasource_alias == "ds_test"  # 从 source_config.alias 推导


def test_extract_datasource_configs_from_objects() -> None:
    """从对象 source_config 提取 DataSourceConfig，按 alias 去重。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "obj1",
                "object_name": "对象1",
                "source_type": "DB",
                "table_name": "t1",
                "source_config": {
                    "alias": "ds_crm",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/crm",
                    "user": "root",
                    "password": "secret",
                    "pool_min": 1,
                    "pool_max": 5,
                },
                "fields": [],
                "actions": [],
            },
            {
                "object_code": "obj2",
                "object_name": "对象2",
                "source_type": "DB",
                "table_name": "t2",
                "source_config": {
                    "alias": "ds_crm",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/crm",
                    "user": "root",
                    "password": "secret",
                },
                "fields": [],
                "actions": [],
            },
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    configs = loader._extract_datasource_configs_from_objects()
    assert len(configs) == 1
    assert "ds_crm" in configs
    assert configs["ds_crm"].db_type == "MYSQL"
    assert configs["ds_crm"].jdbc_url == "jdbc:mysql://localhost:3306/crm"


def test_load_from_content_parses_term_meta_in_fields_and_params() -> None:
    """termMeta 解析为 term_set、term_type、dataset_id。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "obj_term",
                "object_name": "术语对象",
                "source_type": "DB",
                "table_name": "t",
                "fields": [
                    {
                        "field_code": "dept",
                        "field_name": "部门",
                        "field_type": "STRING",
                        "termMeta": {
                            "datasetId": 100,
                            "termMasterType": "dict",
                            "termTypeCode": "dept",
                            "termField": "code",
                        },
                    },
                ],
                "actions": [
                    {
                        "action_code": "query",
                        "action_name": "查询",
                        "params": [
                            {
                                "param_code": "user",
                                "param_name": "用户",
                                "param_type": "STRING",
                                "termMeta": {
                                    "datasetId": 200,
                                    "termMasterType": "list",
                                    "termTypeCode": "user",
                                    "termField": "code",
                                },
                            },
                        ],
                        "function_refs": [],
                    },
                ],
            },
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    cls = loader.get_ontology_class("obj_term")
    # field: dict -> enum, term_set = dept.code
    f = cls.fields[0]
    assert f.term_set == "dept.code"
    assert f.term_type == "enum"
    assert f.dataset_id == 100
    # param: list -> lookup, term_set = user.code
    p = cls.actions[0].params[0]
    assert p.term_set == "user.code"
    assert p.term_type == "lookup"
    assert p.dataset_id == 200


def test_load_from_content_auto_injects_datasource_configs() -> None:
    """load_from_content 完成后，datasource_configs 自动注入。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "obj1",
                "object_name": "对象1",
                "source_type": "DB",
                "table_name": "t1",
                "source_config": {
                    "alias": "ds_test",
                    "db_type": "SQLITE",
                    "jdbc_url": "jdbc:sqlite::memory:",
                },
                "fields": [],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    assert loader._config.datasource_configs
    assert "ds_test" in loader._config.datasource_configs
