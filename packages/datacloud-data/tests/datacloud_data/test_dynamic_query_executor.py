"""Tests for DynamicQueryExecutor."""

import pytest
from datacloud_data_sdk.executor.dynamic_query_executor import DynamicQueryExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


@pytest.fixture
def sqlite_loader() -> OntologyLoader:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "test_obj",
                    "object_name": "测试对象",
                    "source_type": "DB",
                    "source_config": {
                        "alias": "test_db",
                        "db_type": "SQLITE",
                        "jdbc_url": "jdbc:sqlite::memory:",
                    },
                    "table_name": "test_table",
                    "fields": [
                        {
                            "field_code": "id",
                            "field_name": "主键ID",
                            "field_type": "INTEGER",
                            "source_column": "id",
                        },
                        {
                            "field_code": "name",
                            "field_name": "名称",
                            "field_type": "STRING",
                            "source_column": "name",
                        },
                        {
                            "field_code": "amount",
                            "field_name": "金额",
                            "field_type": "NUMBER",
                            "source_column": "amount",
                        },
                    ],
                }
            ],
        }
    )
    return loader


@pytest.fixture
async def executor_with_data(
    sqlite_loader: OntologyLoader,
) -> tuple[DynamicQueryExecutor, OntologyLoader]:
    """初始化 SQLite 内存库并插入测试数据，返回使用同一 ds_manager 的 executor。"""
    ds_manager = DataSourceManager(sqlite_loader._config.datasource_configs)
    connector = ds_manager.get_connector("test_db")
    await connector.execute("CREATE TABLE test_table (id INTEGER, name TEXT, amount REAL)")
    await connector.execute("INSERT INTO test_table VALUES (1, 'a', 10), (2, 'b', 20)")
    executor = DynamicQueryExecutor(sqlite_loader, ds_manager=ds_manager)
    return executor, sqlite_loader


@pytest.mark.asyncio
async def test_execute_db_no_aggregates(
    executor_with_data: tuple[DynamicQueryExecutor, OntologyLoader],
) -> None:
    executor, _ = executor_with_data
    result = await executor.execute("test_obj", {"filters": {}})
    assert "records" in result
    assert "total" in result
    assert result["total"] == 2
    assert len(result["records"]) == 2
    assert result["records"][0]["id"] == 1
    assert result["records"][0]["name"] == "a"
    assert "meta" in result
    assert result["meta"]["viewId"] == "auto_view"
    assert result["meta"]["total"] == 2
    assert result["meta"]["columns"] == [
        {"name": "id", "label": "主键ID", "type": "integer"},
        {"name": "name", "label": "名称", "type": "string"},
        {"name": "amount", "label": "金额", "type": "number"},
    ]


@pytest.mark.asyncio
async def test_execute_db_with_filters(
    executor_with_data: tuple[DynamicQueryExecutor, OntologyLoader],
) -> None:
    """带 filters 时使用参数化查询。"""
    executor, _ = executor_with_data
    result = await executor.execute(
        "test_obj",
        {"filters": {"name": {"op": "eq", "value": "a"}}},
    )
    assert result["total"] == 1
    assert result["records"][0]["name"] == "a"


@pytest.mark.asyncio
async def test_execute_db_aggregates_meta_columns(
    executor_with_data: tuple[DynamicQueryExecutor, OntologyLoader],
) -> None:
    """聚合查询时 meta.columns 含 group_by 字段 + 聚合列。"""
    executor, _ = executor_with_data
    result = await executor.execute(
        "test_obj",
        {
            "filters": {},
            "aggregates": [{"field": "amount", "func": "sum", "as": "金额汇总"}],
            "group_by": ["name"],
        },
    )
    assert "meta" in result
    assert result["meta"]["columns"] == [
        {"name": "name", "label": "名称", "type": "string"},
        {"name": "金额汇总", "label": "金额汇总", "type": "number"},
    ]


@pytest.mark.asyncio
async def test_execute_db_with_limit_offset(
    executor_with_data: tuple[DynamicQueryExecutor, OntologyLoader],
) -> None:
    """limit/offset 生效时返回分页后的 records。"""
    executor, _ = executor_with_data
    result = await executor.execute(
        "test_obj",
        {"filters": {}, "limit": 1, "offset": 1},
    )
    assert result["total"] == 1
    assert len(result["records"]) == 1
    assert result["records"][0]["id"] == 2
    assert result["records"][0]["name"] == "b"
