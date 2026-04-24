from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from datacloud_data_sdk.executor.local_federation_engine import LocalFederationTable
from datacloud_data_sdk.executor.sqlite_local_federation_engine import SQLiteLocalFederationEngine
from datacloud_data_sdk.executor.view_analyze_executor import ViewAnalyzeExecutor
from datacloud_data_sdk.executor.view_lookup_executor import ViewLookupExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.virtual_action.models import ViewFieldMeta
from datacloud_data_sdk.virtual_action.validator import VirtualActionValidationError


def _init_sqlite_db(path: Path, ddl: str, rows: list[tuple[object, ...]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(ddl)
        if rows:
            placeholders = ", ".join("?" for _ in rows[0])
            table_name = "users" if "users" in ddl else "orders"
            conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
        conn.commit()
    finally:
        conn.close()


def _build_loader() -> OntologyLoader:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "users",
                    "object_name": "用户",
                    "description": "用户表",
                    "source_type": "DB",
                    "datasource_alias": "db_users",
                    "table_name": "users",
                    "fields": [
                        {
                            "field_code": "id",
                            "field_name": "用户ID",
                            "field_type": "INTEGER",
                            "is_primary_key": True,
                            "source_column": "id",
                        },
                        {
                            "field_code": "user_name",
                            "field_name": "用户名",
                            "field_type": "STRING",
                            "source_column": "user_name",
                        },
                    ],
                    "actions": [],
                },
                {
                    "object_code": "orders",
                    "object_name": "订单",
                    "description": "订单表",
                    "source_type": "DB",
                    "datasource_alias": "db_orders",
                    "table_name": "orders",
                    "fields": [
                        {
                            "field_code": "order_id",
                            "field_name": "订单ID",
                            "field_type": "INTEGER",
                            "is_primary_key": True,
                            "source_column": "order_id",
                        },
                        {
                            "field_code": "user_id",
                            "field_name": "用户ID",
                            "field_type": "INTEGER",
                            "source_column": "user_id",
                        },
                        {
                            "field_code": "amount",
                            "field_name": "订单金额",
                            "field_type": "DOUBLE",
                            "source_column": "amount",
                        },
                    ],
                    "actions": [],
                },
            ],
            "relations": [
                {
                    "relation_code": "users_to_orders",
                    "relation_name": "用户订单",
                    "source_class": "users",
                    "target_class": "orders",
                    "relation_type": "ONE_TO_MANY",
                    "join_keys": [{"from_field": "id", "to_field": "user_id"}],
                    "description": "用户与订单关联",
                }
            ],
        }
    )
    loader.load_scene(
        {
            "view_id": "cross_db_view",
            "view_name": "跨库用户订单视图",
            "description": "跨两个 SQLite 数据源的测试视图",
            "objects": [{"object_code": "users"}, {"object_code": "orders"}],
            "fields": [
                ViewFieldMeta(
                    property_code="user_id",
                    property_name="用户ID",
                    source_object_code="users",
                    source_object_column_code="id",
                    field_type="INTEGER",
                ),
                ViewFieldMeta(
                    property_code="user_name",
                    property_name="用户名",
                    source_object_code="users",
                    source_object_column_code="user_name",
                    field_type="STRING",
                ),
                ViewFieldMeta(
                    property_code="order_id",
                    property_name="订单ID",
                    source_object_code="orders",
                    source_object_column_code="order_id",
                    field_type="INTEGER",
                ),
                ViewFieldMeta(
                    property_code="order_user_id",
                    property_name="订单用户ID",
                    source_object_code="orders",
                    source_object_column_code="user_id",
                    field_type="INTEGER",
                ),
                ViewFieldMeta(
                    property_code="order_amount",
                    property_name="订单金额",
                    source_object_code="orders",
                    source_object_column_code="amount",
                    field_type="DOUBLE",
                    analytic_role="measure",
                    analytic_kind="raw_number",
                ),
            ],
        }
    )
    return loader


@pytest.fixture
def cross_db_context(tmp_path: Path) -> tuple[OntologyLoader, DataSourceManager]:
    users_db = tmp_path / "users.sqlite3"
    orders_db = tmp_path / "orders.sqlite3"
    _init_sqlite_db(
        users_db,
        "CREATE TABLE users (id INTEGER PRIMARY KEY, user_name TEXT);",
        [(1, "Alice"), (2, "Bob")],
    )
    _init_sqlite_db(
        orders_db,
        "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL);",
        [(101, 1, 10.0), (102, 2, 20.0)],
    )

    loader = _build_loader()
    ds_manager = DataSourceManager(
        {
            "db_users": DataSourceConfig(
                alias="db_users",
                db_type="SQLITE",
                jdbc_url=f"jdbc:sqlite:{users_db}",
            ),
            "db_orders": DataSourceConfig(
                alias="db_orders",
                db_type="SQLITE",
                jdbc_url=f"jdbc:sqlite:{orders_db}",
            ),
        }
    )
    return loader, ds_manager


@pytest.mark.asyncio
async def test_cross_db_view_lookup_single_source_short_circuit(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")

    result = await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name"],
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    assert result["records"] == [{"user_name": "Alice"}, {"user_name": "Bob"}]
    assert result["meta"]["columns"] == [
        {"name": "user_name", "label": "用户名", "type": "string"},
    ]


@pytest.mark.asyncio
async def test_cross_db_view_lookup_federated_join(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")

    result = await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name", "order_amount"],
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    assert result["records"] == [
        {"user_name": "Alice", "order_amount": 10.0},
        {"user_name": "Bob", "order_amount": 20.0},
    ]


@pytest.mark.asyncio
async def test_cross_db_view_lookup_warms_join_keys(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
    caplog: pytest.LogCaptureFixture,
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")
    caplog.set_level(logging.WARNING, logger="datacloud_data_sdk.sql_executor.data_source_manager")

    await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name", "order_amount"],
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    sql_logs = [record.message for record in caplog.records if "SQL:" in record.message]
    assert any('FROM "orders" WHERE user_id IN (' in msg for msg in sql_logs)


@pytest.mark.asyncio
async def test_cross_db_view_analyze_federated_join(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")

    result = await ViewAnalyzeExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "dimensions": [{"field": "user_name"}],
            "metrics": [{"field": "order_amount", "agg": "sum", "as": "total_amount"}],
            "order_by": [{"field": "total_amount", "direction": "desc"}],
            "limit": 10,
        },
    )

    assert result["records"] == [
        {"user_name": "Bob", "total_amount": 20.0},
        {"user_name": "Alice", "total_amount": 10.0},
    ]


@pytest.mark.asyncio
async def test_cross_db_view_analyze_requires_metrics(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")

    with pytest.raises(VirtualActionValidationError, match="metrics 不能为空"):
        await ViewAnalyzeExecutor(loader, ds_manager=ds_manager).execute(
            view,
            {
                "dimensions": [{"field": "user_name"}],
                "limit": 10,
            },
        )


@pytest.mark.asyncio
async def test_cross_db_view_analyze_respects_view_field_group_ops(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")
    user_name_field = next(field for field in view.fields if field.property_code == "user_name")
    user_name_field.group_ops = ["self"]

    with pytest.raises(VirtualActionValidationError, match="不支持分组方式 'month'"):
        await ViewAnalyzeExecutor(loader, ds_manager=ds_manager).execute(
            view,
            {
                "dimensions": [{"field": "user_name", "group_op": "month"}],
                "metrics": [{"field": "order_amount", "agg": "sum", "as": "total_amount"}],
                "limit": 10,
            },
        )


@pytest.mark.asyncio
async def test_cross_db_view_lookup_pushes_down_and_filters(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
    caplog: pytest.LogCaptureFixture,
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")
    caplog.set_level(logging.WARNING, logger="datacloud_data_sdk.sql_executor.data_source_manager")

    result = await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name", "order_amount"],
            "filters": [
                {"field": "user_name", "op": "eq", "value": "Alice"},
                {"field": "order_amount", "op": "gt", "value": 5},
            ],
            "filter_relation": "AND",
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    sql_logs = [record.message for record in caplog.records if "SQL:" in record.message]
    assert any("FROM \"users\" WHERE user_name = 'Alice'" in msg for msg in sql_logs)
    assert any('FROM "orders" WHERE amount > 5' in msg for msg in sql_logs)
    assert result["records"] == [{"user_name": "Alice", "order_amount": 10.0}]


@pytest.mark.asyncio
async def test_cross_db_view_lookup_does_not_push_down_cross_object_or_filters(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
    caplog: pytest.LogCaptureFixture,
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")
    caplog.set_level(logging.WARNING, logger="datacloud_data_sdk.sql_executor.data_source_manager")

    result = await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name", "order_amount"],
            "filters": [
                {"field": "user_name", "op": "eq", "value": "Alice"},
                {"field": "order_amount", "op": "gt", "value": 15},
            ],
            "filter_relation": "OR",
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    sql_logs = [record.message for record in caplog.records if "SQL:" in record.message]
    assert any('FROM "users"' in msg for msg in sql_logs)
    assert any('FROM "orders"' in msg for msg in sql_logs)
    assert not any('FROM "users" WHERE user_name =' in msg for msg in sql_logs)
    assert not any('FROM "orders" WHERE amount >' in msg for msg in sql_logs)
    assert result["records"] == [
        {"user_name": "Alice", "order_amount": 10.0},
        {"user_name": "Bob", "order_amount": 20.0},
    ]


@pytest.mark.asyncio
async def test_cross_db_view_lookup_ignores_row_guard_threshold(
    cross_db_context: tuple[OntologyLoader, DataSourceManager],
) -> None:
    loader, ds_manager = cross_db_context
    view = loader.get_view("cross_db_view")
    loader._config.federated_row_guard_threshold = 1

    result = await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["user_name", "order_amount"],
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    assert result["records"] == [
        {"user_name": "Alice", "order_amount": 10.0},
        {"user_name": "Bob", "order_amount": 20.0},
    ]


@pytest.mark.asyncio
async def test_sqlite_local_federation_engine_normalizes_decimal_values(tmp_path: Path) -> None:
    engine = SQLiteLocalFederationEngine()

    runtime = engine.materialize_tables(
        {
            "orders": LocalFederationTable(
                columns=["order_id", "amount"],
                rows=[{"order_id": 1, "amount": Decimal("10.50")}],
                column_types={"order_id": "INTEGER", "amount": "REAL"},
            )
        }
    )

    try:
        rows = await runtime.datasource_manager.get_connector(runtime.datasource_alias).execute(
            'SELECT "order_id", "amount" FROM "orders"'
        )
    finally:
        await runtime.close()

    assert rows == [{"order_id": 1, "amount": 10.5}]
