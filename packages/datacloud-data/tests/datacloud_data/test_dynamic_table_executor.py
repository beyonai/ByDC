from __future__ import annotations

from typing import Any

import pytest
from datacloud_data_sdk.executor.dynamic_table_executor import DynamicTableExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyClass, OntologyField
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


class _CaptureConnector(BaseSourceConnector):
    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.select_rows: list[dict[str, Any]] = []

    @classmethod
    def supported_type(cls) -> str:
        return "CAPTURE"

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        if sql.startswith("SELECT"):
            return self.select_rows
        return []

    async def test_connection(self) -> bool:
        return True


def _loader() -> tuple[OntologyLoader, _CaptureConnector]:
    loader = OntologyLoader()
    cls = OntologyClass(
        object_code="sales_note",
        object_name="销售记录",
        description="",
        source_type="DYNAMIC_TABLE",
        datasource_alias="dynamic_table",
        table_name="sales_note",
        fields=[
            OntologyField("id", "ID", "INTEGER", is_primary_key=True),
            OntologyField("customer_name", "客户名称", "STRING", required=True),
            OntologyField("amount", "金额", "NUMBER"),
        ],
        actions=[],
    )
    loader._classes[cls.object_code] = cls
    config = DataSourceConfig(alias="dynamic_table", db_type="SQLITE")
    loader.configure(datasource_configs={"dynamic_table": config})
    connector = _CaptureConnector(config)
    return loader, connector


@pytest.mark.asyncio
async def test_dynamic_table_insert_excludes_generated_primary_key() -> None:
    loader, connector = _loader()
    ds = DataSourceManager({"dynamic_table": connector.config})
    ds._connectors["dynamic_table"] = connector

    result = await DynamicTableExecutor(loader, ds).insert(
        "sales_note",
        {"records": [{"customer_name": "白银有色", "amount": "12.5"}]},
    )

    sql, params = connector.calls[0]
    assert sql == 'INSERT INTO "sales_note" ("customer_name", "amount") VALUES (:v_0, :v_1)'
    assert params == {"v_0": "白银有色", "v_1": 12.5}
    assert result["records"] == [{"customer_name": "白银有色", "amount": "12.5"}]


@pytest.mark.asyncio
async def test_dynamic_table_update_returns_updated_rows() -> None:
    loader, connector = _loader()
    connector.select_rows = [{"id": 1, "customer_name": "新客户", "amount": 20}]
    ds = DataSourceManager({"dynamic_table": connector.config})
    ds._connectors["dynamic_table"] = connector

    result = await DynamicTableExecutor(loader, ds).update(
        "sales_note",
        {
            "values": {"customer_name": "新客户"},
            "filters": [{"field": "id", "op": "eq", "value": 1}],
        },
    )

    assert (
        connector.calls[0][0] == 'UPDATE "sales_note" SET "customer_name" = :u_0 WHERE id = :p_id_0'
    )
    assert connector.calls[1][0].startswith(
        'SELECT "id" AS "id", "customer_name" AS "customer_name"'
    )
    assert result["records"] == [{"id": 1, "customer_name": "新客户", "amount": 20}]


@pytest.mark.asyncio
async def test_dynamic_table_delete_returns_pre_delete_rows() -> None:
    loader, connector = _loader()
    connector.select_rows = [{"id": 1, "customer_name": "待删除", "amount": 20}]
    ds = DataSourceManager({"dynamic_table": connector.config})
    ds._connectors["dynamic_table"] = connector

    result = await DynamicTableExecutor(loader, ds).delete(
        "sales_note",
        {"filters": [{"field": "id", "op": "eq", "value": 1}]},
    )

    assert connector.calls[0][0].startswith('SELECT "id" AS "id"')
    assert connector.calls[1][0] == 'DELETE FROM "sales_note" WHERE id = :p_id_0'
    assert result["records"] == [{"id": 1, "customer_name": "待删除", "amount": 20}]
