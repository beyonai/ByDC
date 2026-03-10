import pytest
from pathlib import Path
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.context import InvocationContext

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "source_config": {
                "alias": "test_db",
                "db_type": "SQLITE",
                "jdbc_url": "jdbc:sqlite::memory:",
            },
            "datasource_alias": "test_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING"},
            ],
            "actions": [],
        }
    ],
    "relations": [],
}

MOCK_PLAN_DICT = {
    "question": "查商机",
    "can_answer": True,
    "steps": [
        {
            "step_id": "s1",
            "type": "SQL",
            "source_id": "SRC_TEST_DB",
            "datasource_alias": "test_db",
            "sql_template": "SELECT '1' AS bo_id, '5G项目' AS bo_name",
            "output_ref": "bo_list",
        }
    ],
    "aggregation": {
        "strategy": "DIRECT",
        "final_step_id": "s1",
        "columns": [
            {"name": "bo_id", "label": "商机ID", "type": "string"},
            {"name": "bo_name", "label": "商机名称", "type": "string"},
        ],
    },
}


@pytest.mark.asyncio
async def test_object_query_returns_records(tmp_path: Path) -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.configure(
        plan_generator=MockPlanGenerator(fixed_plan=MOCK_PLAN_DICT),
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
            )
        },
        csv_base_dir=str(tmp_path),
    )
    obj = loader.get_object("sales_bo")
    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机")
    assert len(result["records"]) == 1
    assert result["records"][0]["bo_name"] == "5G项目"
