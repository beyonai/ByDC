"""ByClaw sqlExecute connector tests — fixed personal_object.db."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any, Generator

import pytest
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry
from datacloud_data_sdk.sql_executor.connectors.byclaw_sql_execute_connector import (
    ByclawSqlExecuteConnector,
)
from datacloud_data_sdk.sql_executor.data_source_manager import (
    DataSourceManager,
    _LoggingConnectorProxy,
)
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


def _make_config(*, alias: str = "dynamic_table") -> DataSourceConfig:
    return DataSourceConfig(
        alias=alias,
        db_type="SQLITE",
        connector_type="BYCLAW_SQL_EXECUTE",
    )


def _unwrap(connector: Any) -> Any:
    if isinstance(connector, _LoggingConnectorProxy):
        return connector._real  # type: ignore[attr-defined]
    return connector


@pytest.fixture
def tmp_mount() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as td:
        ByclawSqlExecuteConnector.configure_mount_path(td)
        yield td
    ByclawSqlExecuteConnector.configure_mount_path(None)


def _init_db(mount: str) -> None:
    db_dir = os.path.join(mount, "byclaw-datacloud")
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(db_dir, "personal_object.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, 'alice')")
    conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (2, 'bob')")
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_execute(tmp_mount: str) -> None:
    _init_db(tmp_mount)
    connector = ByclawSqlExecuteConnector(_make_config())
    records = await connector.execute("SELECT * FROM users ORDER BY id")
    assert records == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
    await connector.close()


@pytest.mark.asyncio
async def test_params_are_bound(tmp_mount: str) -> None:
    _init_db(tmp_mount)
    connector = ByclawSqlExecuteConnector(_make_config())
    records = await connector.execute("SELECT name FROM users WHERE id = :uid", {"uid": 2})
    assert records == [{"name": "bob"}]
    await connector.close()


@pytest.mark.asyncio
async def test_shared_db(tmp_mount: str) -> None:
    _init_db(tmp_mount)
    c1 = ByclawSqlExecuteConnector(_make_config(alias="a"))
    c2 = ByclawSqlExecuteConnector(_make_config(alias="b"))
    assert await c1.execute("SELECT COUNT(*) AS cnt FROM users") == [{"cnt": 2}]
    assert await c2.execute("SELECT COUNT(*) AS cnt FROM users") == [{"cnt": 2}]
    await c1.close()
    await c2.close()


@pytest.mark.asyncio
async def test_test_connection(tmp_mount: str) -> None:
    _init_db(tmp_mount)
    connector = ByclawSqlExecuteConnector(_make_config())
    assert await connector.test_connection() is True
    await connector.close()


@pytest.mark.asyncio
async def test_test_connection_new_db(tmp_mount: str) -> None:
    os.makedirs(os.path.join(tmp_mount, "byclaw-datacloud"), exist_ok=True)
    connector = ByclawSqlExecuteConnector(_make_config())
    assert await connector.test_connection() is True
    await connector.close()


@pytest.mark.asyncio
async def test_mount_path_from_env(tmp_mount: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_MINIO_MOUNT_PATH", tmp_mount)
    ByclawSqlExecuteConnector.configure_mount_path(None)
    _init_db(tmp_mount)
    connector = ByclawSqlExecuteConnector(_make_config())
    assert await connector.execute("SELECT 1 AS env") == [{"env": 1}]
    await connector.close()


def test_registered_by_default() -> None:
    assert ConnectorRegistry.get("BYCLAW_SQL_EXECUTE") is ByclawSqlExecuteConnector


@pytest.mark.asyncio
async def test_manager_uses_byclaw_connector(tmp_mount: str) -> None:
    _init_db(tmp_mount)
    manager = DataSourceManager({"dyn": _make_config()})
    assert isinstance(_unwrap(manager.get_connector("dyn")), ByclawSqlExecuteConnector)
