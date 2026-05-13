from __future__ import annotations

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.models import QueryExecutionPlan, parse_plan
from datacloud_data_sdk.plan.query_plan_generator import BasePlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

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
    "views": [
        {
            "view_id": "sales_view",
            "view_name": "销售视图",
            "description": "销售商机视图",
            "objects": ["sales_bo"],
        }
    ],
}

FIXED_PLAN = {
    "question": "查商机",
    "can_answer": True,
    "steps": [
        {
            "step_id": "s1",
            "type": "SQL",
            "source_id": "SRC_TEST_DB",
            "datasource_alias": "test_db",
            "sql_template": "SELECT '1' AS bo_id, '项目A' AS bo_name",
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


class CapturePlanGenerator(BasePlanGenerator):
    def __init__(self) -> None:
        self.captured_knowledge_context: str | None = None

    async def generate(
        self,
        payload,
        question: str,
        knowledge_context: str | None = None,
        validation_errors=None,
        term_loader=None,
    ) -> QueryExecutionPlan:
        self.captured_knowledge_context = knowledge_context
        return parse_plan(FIXED_PLAN, question)


def _build_loader(tmp_path) -> tuple[OntologyLoader, CapturePlanGenerator]:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    generator = CapturePlanGenerator()
    loader.configure(
        plan_generator=generator,
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
            )
        },
        csv_base_dir=str(tmp_path),
    )
    return loader, generator


@pytest.mark.asyncio
async def test_object_query_forwards_knowledge_context(tmp_path) -> None:
    loader, generator = _build_loader(tmp_path)
    obj = loader.get_object("sales_bo")

    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机", knowledge_context="商机口径：按最新阶段统计")

    assert generator.captured_knowledge_context == "商机口径：按最新阶段统计"
    assert result["records"][0]["bo_name"] == "项目A"


@pytest.mark.asyncio
async def test_view_query_forwards_knowledge_context(tmp_path) -> None:
    loader, generator = _build_loader(tmp_path)
    view = loader.get_view("sales_view")

    with InvocationContext(tenant_id="t1"):
        result = await view.query("查商机", knowledge_context="只看重点项目")

    assert generator.captured_knowledge_context == "只看重点项目"
    assert result["records"][0]["bo_id"] == "1"
