import json
import logging

from fastapi.testclient import TestClient

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

HEADERS = {
    "X-Tenant-Id": "t1",
    "X-User-Id": "u1",
    "X-Session-Id": "s1",
    "Authorization": "Bearer tok",
    "X-System-Code": "dc",
}

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

MOCK_PLAN = {
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


def _create_test_app(tmp_path=None, trigger_lifespan_first: bool = False):
    """创建测试 app。若 trigger_lifespan_first=True，会先发请求触发 lifespan，再替换 loader 并注入 event_bus。"""
    from datacloud_data_service.api.routes import create_app

    app = create_app()
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    csv_dir = str(tmp_path) if tmp_path else "/tmp/datacloud_csv_test"
    if trigger_lifespan_first:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/health")  # 触发 lifespan，使 app.state.event_bus 可用
    loader.configure(
        plan_generator=MockPlanGenerator(fixed_plan=MOCK_PLAN),
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
            )
        },
        csv_base_dir=csv_dir,
        event_bus=getattr(app.state, "event_bus", None),
    )
    app.state.loader = loader
    return app


def test_rest_query_returns_response(tmp_path) -> None:
    app = _create_test_app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/query",
        json={"question": "查商机"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["message"] == "success"


def test_rest_query_missing_tenant_returns_400() -> None:
    from datacloud_data_service.api.routes import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/query",
        json={"question": "查商机"},
    )
    assert resp.status_code == 400


def test_rest_query_no_loader_returns_error() -> None:
    from datacloud_data_service.api.routes import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/query",
        json={"question": "查商机"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 500
    assert "not initialized" in data["message"]


def test_rest_query_emits_query_performance_log(caplog, tmp_path) -> None:
    """验证 /api/v1/query 成功时 stdout 有 query_performance JSON 日志。"""
    caplog.set_level(logging.INFO, logger="datacloud_data_service.api.routes")
    app = _create_test_app(tmp_path, trigger_lifespan_first=True)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/query",
        json={"question": "查商机"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    perf_logs = [r.msg for r in caplog.records if "query_performance" in r.msg]
    assert len(perf_logs) >= 1
    data = json.loads(perf_logs[0])
    assert data["event"] == "query_performance"
    assert "request_id" in data
    assert "stages" in data
    assert "total_ms" in data
