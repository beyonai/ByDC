"""CRM 端到端场景测试。"""
import pytest
from pathlib import Path

from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import CannotAnswerError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


REGISTRY_PATH = Path(__file__).parent.parent.parent / "resources" / "ontology" / "crm_demo" / "objects_registry.json"


def _make_loader(plan_dict: dict, tmp_path: Path) -> OntologyLoader:
    loader = OntologyLoader()
    if REGISTRY_PATH.exists():
        loader.load_from_path(REGISTRY_PATH)
    else:
        # Fallback minimal registry for CI
        loader.load_from_content({
            "functions": [],
            "objects": [
                {
                    "object_code": "sales_business_opportunity",
                    "object_name": "商机",
                    "source_type": "DB",
                    "source_config": {
                        "alias": "crm_db",
                        "db_type": "SQLITE",
                        "jdbc_url": "jdbc:sqlite::memory:",
                    },
                    "datasource_alias": "crm_db",
                    "table_name": "sales_business_opportunity",
                    "fields": [
                        {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                        {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING"},
                        {"field_code": "owner_id", "field_name": "负责人", "field_type": "STRING"},
                    ],
                    "actions": [
                        {
                            "action_code": "calc_score",
                            "action_name": "计算评分",
                            "script": "def execute(params):\n    return {'score': 85}",
                            "function_refs": [],
                            "params": [
                                {"param_code": "bo_id", "param_type": "STRING", "direction": "IN"},
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        })
    # Inject calc_score action if loaded from real registry (which has no actions)
    cls = loader.get_ontology_class("sales_business_opportunity")
    if not cls.actions:
        from datacloud_data_sdk.ontology.models import OntologyAction, OntologyActionParam
        cls.actions.append(
            OntologyAction(
                action_code="calc_score",
                action_name="计算评分",
                description="计算商机评分",
                belong_class="sales_business_opportunity",
                params=[
                    OntologyActionParam(
                        param_code="bo_id",
                        param_name="商机ID",
                        direction="IN",
                        param_type="STRING",
                        required=False,
                        default_value=None,
                        mapping_path="",
                        term_set=None,
                    ),
                ],
                function_refs=[],
                script="def execute(params):\n    return {'score': 85}",
            )
        )
    loader.configure(
        plan_generator=MockPlanGenerator(fixed_plan=plan_dict),
        datasource_configs={
            "crm_db": DataSourceConfig(alias="crm_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"),
            "ds_crm": DataSourceConfig(alias="ds_crm", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"),
        },
        csv_base_dir=str(tmp_path),
    )
    return loader


@pytest.mark.asyncio
async def test_scenario_1_single_object_query(tmp_path: Path) -> None:
    """场景1：自然语言查询「查商机」→ 返回 records。"""
    plan = {
        "can_answer": True,
        "steps": [{
            "step_id": "s1", "type": "SQL",
            "datasource_alias": "crm_db",
            "sql_template": "SELECT '001' AS bo_id, '5G项目' AS bo_name, 'U001' AS owner_id",
            "output_ref": "bo_list",
        }],
        "aggregation": {
            "strategy": "DIRECT", "final_step_id": "s1",
            "columns": [
                {"name": "bo_id", "label": "商机ID", "type": "string"},
                {"name": "bo_name", "label": "商机名称", "type": "string"},
            ],
        },
    }
    loader = _make_loader(plan, tmp_path)
    obj = loader.get_object("sales_business_opportunity")
    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机")
    assert len(result["records"]) == 1
    assert result["records"][0]["bo_name"] == "5G项目"


@pytest.mark.asyncio
async def test_scenario_2_cannot_answer(tmp_path: Path) -> None:
    """场景2：不可回答 → CannotAnswerError。"""
    plan = {
        "can_answer": False,
        "clarification": "当前视图不包含合同金额字段，无法按金额统计",
    }
    loader = _make_loader(plan, tmp_path)
    obj = loader.get_object("sales_business_opportunity")
    with InvocationContext(tenant_id="t1"):
        with pytest.raises(CannotAnswerError) as exc_info:
            await obj.query("按合同金额统计")
        assert "合同金额" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_3_script_action(tmp_path: Path) -> None:
    """场景3：脚本动作执行。"""
    plan = {"can_answer": True, "steps": [], "aggregation": None}
    loader = _make_loader(plan, tmp_path)
    obj = loader.get_object("sales_business_opportunity")
    with InvocationContext(tenant_id="t1"):
        result = await obj.invoke_action("calc_score", {"bo_id": "B001"})
    assert result["score"] == 85


@pytest.mark.asyncio
async def test_scenario_4_mcp_action_via_service(tmp_path: Path) -> None:
    """场景4：通过 MCP tools/call 调用脚本动作。"""
    from fastapi.testclient import TestClient
    from datacloud_data_service.api.routes import create_app

    plan = {"can_answer": True, "steps": [], "aggregation": None}
    loader = _make_loader(plan, tmp_path)

    app = create_app()
    app.state.loader = loader
    client = TestClient(app)

    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "1", "method": "tools/call",
        "params": {"name": "calc_score", "arguments": {"bo_id": "B001"}},
    }, headers={"X-Tenant-Id": "t1"})

    result = resp.json()["result"]
    assert result["isError"] is False
    assert "85" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_scenario_5_get_description(tmp_path: Path) -> None:
    """验证 Object.get_description() 包含字段和动作信息。"""
    plan = {"can_answer": True, "steps": [], "aggregation": None}
    loader = _make_loader(plan, tmp_path)
    obj = loader.get_object("sales_business_opportunity")
    desc = obj.get_description()
    assert "商机" in desc
    assert "calc_score" in desc
