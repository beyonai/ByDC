"""数据源连接器抽象基类。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


class BaseSourceConnector(ABC):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    @classmethod
    @abstractmethod
    def supported_type(cls) -> str:
        ...

    @abstractmethod
    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        ...

    async def close(self) -> None:
        pass
