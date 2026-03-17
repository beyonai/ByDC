from fastapi.testclient import TestClient

from datacloud_data.sql_executor.models import DataSourceConfig


def test_health_check() -> None:
    from datacloud_data_service.api.routes import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_check_with_datasources() -> None:
    """当配置了数据源时，/health 返回 datasources 健康状态。"""
    from datacloud_data_service.api.routes import create_app

    datasource_configs = {
        "crm_db": DataSourceConfig(
            alias="crm_db",
            db_type="SQLITE",
            jdbc_url="jdbc:sqlite::memory:",
        ),
    }
    with TestClient(create_app(datasource_configs=datasource_configs)) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "datasources" in data
    assert data["datasources"]["crm_db"] == "ok"
