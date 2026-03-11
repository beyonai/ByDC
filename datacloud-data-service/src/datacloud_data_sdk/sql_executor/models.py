"""SQL 执行器相关模型。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataSourceConfig:
    alias: str
    db_type: str  # SQLITE / MYSQL / POSTGRESQL / CLICKHOUSE
    jdbc_url: str = ""
    user: str = ""
    password: str = ""
    pool_min: int = 1
    pool_max: int = 5
    pool_timeout: float = 30.0


@dataclass
class SqlExecResult:
    csv_path: str
    row_count: int = 0
