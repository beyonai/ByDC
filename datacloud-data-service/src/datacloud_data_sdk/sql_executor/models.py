"""SQL 执行器相关模型。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataSourceConfig:
    alias: str
    db_type: str  # SQLITE / MYSQL / POSTGRESQL / OPENGAUSS / CLICKHOUSE
    jdbc_url: str = ""
    user: str = ""
    password: str = ""
    pool_min: int = 1
    pool_max: int = 5
    pool_timeout: float = 30.0
    open_gauss_compat: bool = False  # 当 db_type=POSTGRESQL 且实际为 openGauss 时启用


@dataclass
class SqlExecResult:
    csv_path: str
    row_count: int = 0
