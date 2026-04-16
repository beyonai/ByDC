import pytest
from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry
from datacloud_data_sdk.sql_executor.connectors.sqlite_connector import SQLiteConnector


def test_sqlite_connector_registered_by_default() -> None:
    cls = ConnectorRegistry.get("SQLITE")
    assert cls is SQLiteConnector


def test_register_custom_connector() -> None:
    class MyConnector(SQLiteConnector):
        @classmethod
        def supported_type(cls) -> str:
            return "CUSTOM_DB"

    ConnectorRegistry.register("CUSTOM_DB", MyConnector)
    assert ConnectorRegistry.get("CUSTOM_DB") is MyConnector


def test_unknown_type_raises() -> None:
    with pytest.raises(DataSourceUnavailableError):
        ConnectorRegistry.get("NONEXISTENT_DB")
