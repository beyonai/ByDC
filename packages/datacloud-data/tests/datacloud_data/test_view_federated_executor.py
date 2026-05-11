from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from datacloud_data_sdk.executor.local_federation_engine import LocalFederationTable
from datacloud_data_sdk.executor.sqlite_local_federation_engine import SQLiteLocalFederationEngine
from datacloud_data_sdk.executor.view_analyze_executor import ViewAnalyzeExecutor
from datacloud_data_sdk.executor.view_lookup_executor import ViewLookupExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.virtual_action.models import ViewFieldMeta
from datacloud_data_sdk.virtual_action.validator import VirtualActionValidationError


def _init_sqlite_db(
    path: Path,
    ddl: str,
    rows: list[tuple[object, ...]],
    table_name: str | None = None,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(ddl)
        if rows:
            placeholders = ", ".join("?" for _ in rows[0])
            target_table = table_name or ("users" if "users" in ddl else "orders")
            conn.executemany(f"INSERT INTO {target_table} VALUES ({placeholders})", rows)
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


def _build_join_key_coercion_loader() -> OntologyLoader:
    """构造用于联邦 join-key 参数类型回归测试的本体。"""
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "parent_orgs",
                    "object_name": "父对象",
                    "description": "父对象",
                    "source_type": "DB",
                    "datasource_alias": "db_parent",
                    "table_name": "parent_orgs",
                    "fields": [
                        {
                            "field_code": "org_code",
                            "field_name": "组织编码",
                            "field_type": "STRING",
                            "source_column": "org_code",
                        },
                        {
                            "field_code": "org_name",
                            "field_name": "组织名称",
                            "field_type": "STRING",
                            "source_column": "org_name",
                        },
                    ],
                    "actions": [],
                },
                {
                    "object_code": "po_organization",
                    "object_name": "组织",
                    "description": "组织",
                    "source_type": "DB",
                    "datasource_alias": "db_orgs",
                    "table_name": "po_organization",
                    "fields": [
                        {
                            "field_code": "org_id",
                            "field_name": "组织ID",
                            "field_type": "INTEGER",
                            "source_column": "org_id",
                        },
                        {
                            "field_code": "org_name",
                            "field_name": "组织名称",
                            "field_type": "STRING",
                            "source_column": "org_name",
                        },
                    ],
                    "actions": [],
                },
            ],
            "relations": [
                {
                    "relation_code": "parent_orgs_to_orgs",
                    "relation_name": "父对象关联组织",
                    "source_class": "parent_orgs",
                    "target_class": "po_organization",
                    "relation_type": "ONE_TO_MANY",
                    "join_keys": [{"from_field": "org_code", "to_field": "org_id"}],
                    "description": "父对象与组织关联",
                }
            ],
        }
    )
    loader.load_scene(
        {
            "view_id": "join_key_coercion_view",
            "view_name": "联邦 join 键回归视图",
            "description": "用于验证联邦执行中整数主键参数归一化",
            "objects": [{"object_code": "parent_orgs"}, {"object_code": "po_organization"}],
            "fields": [
                ViewFieldMeta(
                    property_code="org_code",
                    property_name="组织编码",
                    source_object_code="parent_orgs",
                    source_object_column_code="org_code",
                    field_type="STRING",
                ),
                ViewFieldMeta(
                    property_code="org_name",
                    property_name="组织名称",
                    source_object_code="po_organization",
                    source_object_column_code="org_name",
                    field_type="STRING",
                ),
            ],
        }
    )
    return loader


class _CaptureConnector(BaseSourceConnector):
    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self.sql = ""
        self.params: dict[str, object] | None = None

    @classmethod
    def supported_type(cls) -> str:
        return "capture"

    async def execute(
        self, sql: str, params: dict[str, object] | None = None
    ) -> list[dict[str, object]]:
        self.sql = sql
        self.params = params
        return []

    async def test_connection(self) -> bool:
        return True


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
async def test_cross_db_view_lookup_coerces_join_key_strings_to_integers(
    tmp_path: Path,
) -> None:
    loader = _build_join_key_coercion_loader()
    parent_db = tmp_path / "parent.sqlite3"
    _init_sqlite_db(
        parent_db,
        "CREATE TABLE parent_orgs (org_code TEXT PRIMARY KEY, org_name TEXT);",
        [("231", "杭州总部"), ("234", "上海分部")],
        table_name="parent_orgs",
    )

    capture_connector = _CaptureConnector(DataSourceConfig(alias="db_orgs", db_type="POSTGRESQL"))
    ds_manager = DataSourceManager(
        {
            "db_parent": DataSourceConfig(
                alias="db_parent",
                db_type="SQLITE",
                jdbc_url=f"jdbc:sqlite:{parent_db}",
            ),
            "db_orgs": capture_connector.config,
        }
    )
    ds_manager._connectors["db_orgs"] = capture_connector

    view = loader.get_view("join_key_coercion_view")

    await ViewLookupExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "select": ["org_code", "org_name"],
            "order_by": [{"field": "org_name", "direction": "asc"}],
            "limit": 10,
        },
    )

    assert capture_connector.params is not None
    assert capture_connector.sql.startswith("SELECT ")
    param_values = list(capture_connector.params.values())
    int_values = [value for value in param_values if isinstance(value, int)]
    assert len(int_values) == len(param_values)
    assert sorted(int_values) == [231, 234]


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
async def test_view_analyze_orders_time_group_by_selected_alias() -> None:
    loader = _build_loader()
    view = loader.get_view("cross_db_view")
    connector = _CaptureConnector(DataSourceConfig(alias="db_users", db_type="POSTGRESQL"))
    ds_manager = DataSourceManager({"db_users": connector.config, "db_orders": connector.config})
    ds_manager._connectors["db_users"] = connector

    await ViewAnalyzeExecutor(loader, ds_manager=ds_manager).execute(
        view,
        {
            "dimensions": [{"field": "user_name", "group_op": "month"}],
            "metrics": [{"agg": "count_all", "as": "project_count"}],
            "order_by": [{"field": "user_name", "direction": "asc"}],
            "limit": 100,
        },
    )

    assert 'ORDER BY "user_name_month" ASC' in connector.sql
    assert 'ORDER BY t0."user_name" ASC' not in connector.sql


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
    config = cast(Any, loader._config)
    config.federated_row_guard_threshold = 1

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
