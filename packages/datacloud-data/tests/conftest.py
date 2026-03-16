"""Pytest configuration. Ensures sqlparse is available for tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Add tmp_sqlparse to path if sqlparse is not installed (e.g. when running without [sql] extra)
try:
    import sqlparse  # noqa: F401
except ImportError:
    _tmp_sqlparse = Path(__file__).resolve().parent.parent / "tmp_sqlparse"
    if _tmp_sqlparse.exists():
        sys.path.insert(0, str(_tmp_sqlparse))


# --- GraphQL 场景测试 fixtures (tests/fixtures/ontology/) ---

import pytest

from datacloud_data.ontology.loader import OntologyLoader
from datacloud_data.sql_executor.data_source_manager import DataSourceManager


@pytest.fixture
def load_scenario_db_linked() -> OntologyLoader:
    """加载 scenario_db_linked.json 本体。"""
    path = Path(__file__).resolve().parent / "fixtures" / "ontology" / "scenario_db_linked.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


@pytest.fixture
def load_scenario_api_linked() -> OntologyLoader:
    """加载 scenario_api_linked.json 本体。"""
    path = Path(__file__).resolve().parent / "fixtures" / "ontology" / "scenario_api_linked.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


@pytest.fixture
async def scenario_db_linked_with_data(load_scenario_db_linked: OntologyLoader):
    """加载 scenario_db_linked.json，创建 SQLite 内存表 customer、opportunity，插入测试数据。"""
    loader = load_scenario_db_linked
    ds_manager = DataSourceManager(loader._config.datasource_configs)
    connector = ds_manager.get_connector("test_db")
    await connector.execute(
        "CREATE TABLE customer (id INTEGER, name TEXT, customer_id TEXT)"
    )
    await connector.execute(
        "CREATE TABLE opportunity (id INTEGER, amount REAL, customer_id TEXT)"
    )
    await connector.execute(
        "INSERT INTO customer VALUES (1, 'c1', 'c1'), (2, 'c2', 'c2')"
    )
    await connector.execute(
        "INSERT INTO opportunity VALUES (1, 100, 'c1'), (2, 200, 'c1'), (3, 150, 'c2')"
    )
    return loader, ds_manager


@pytest.fixture
def load_scenario_db_derived() -> OntologyLoader:
    """加载 scenario_db_derived.json 本体。"""
    path = Path(__file__).resolve().parent / "fixtures" / "ontology" / "scenario_db_derived.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


@pytest.fixture
def load_scenario_api_derived() -> OntologyLoader:
    """加载 scenario_api_derived.json 本体。"""
    path = Path(__file__).resolve().parent / "fixtures" / "ontology" / "scenario_api_derived.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


@pytest.fixture
async def scenario_db_derived_with_data(load_scenario_db_derived: OntologyLoader):
    """加载 scenario_db_derived.json，创建 sales_bo、customer、opportunity 表，插入测试数据。"""
    loader = load_scenario_db_derived
    ds_manager = DataSourceManager(loader._config.datasource_configs)
    connector = ds_manager.get_connector("test_db")
    await connector.execute("CREATE TABLE sales_bo (id INTEGER, amount REAL)")
    await connector.execute("CREATE TABLE customer (id INTEGER, name TEXT, customer_id TEXT)")
    await connector.execute("CREATE TABLE opportunity (id INTEGER, amount REAL, customer_id TEXT)")
    await connector.execute("INSERT INTO sales_bo VALUES (1, 100), (2, 200)")
    await connector.execute("INSERT INTO customer VALUES (1, 'c1', 'c1'), (2, 'c2', 'c2')")
    await connector.execute(
        "INSERT INTO opportunity VALUES (1, 100, 'c1'), (2, 200, 'c1'), (3, 150, 'c2')"
    )
    return loader, ds_manager
