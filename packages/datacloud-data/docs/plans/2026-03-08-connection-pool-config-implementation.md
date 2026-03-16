# #38 连接池配置补齐 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使 MySQL / PostgreSQL 连接器的 pool_min、pool_max、pool_timeout 正确映射到 SQLAlchemy。

**Architecture:** 在 DataSourceConfig 新增 pool_timeout；MySQLConnector、PostgreSQLConnector 的 _init_engine 从 config 读取 pool_min、pool_max、pool_timeout，映射为 pool_size、max_overflow、pool_timeout 传入 create_async_engine。

**Tech Stack:** SQLAlchemy create_async_engine、unittest.mock.patch

---

## Task 1: DataSourceConfig 新增 pool_timeout

**Files:**
- Modify: `src/datacloud_data/sql_executor/models.py`

**Step 1:** 在 `DataSourceConfig` 中新增 `pool_timeout: float = 30.0`

```python
@dataclass
class DataSourceConfig:
    alias: str
    db_type: str
    jdbc_url: str = ""
    user: str = ""
    password: str = ""
    pool_min: int = 1
    pool_max: int = 5
    pool_timeout: float = 30.0
```

**Step 2:** 运行 `pytest tests/ -v --tb=short` 确认无回归

**Step 3:** `git add` + `git commit -m "feat(sql): add pool_timeout to DataSourceConfig"`

---

## Task 2: MySQLConnector 使用 pool 配置

**Files:**
- Modify: `src/datacloud_data/sql_executor/connectors/mysql_connector.py`

**Step 1:** 修改 `_init_engine`，从 config 读取并映射：

```python
def _init_engine(self) -> None:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as e:
        raise ImportError(
            "aiomysql not installed. Install with: pip install aiomysql"
        ) from e

    url = _build_sqlalchemy_url(self.config)
    pool_min = getattr(self.config, "pool_min", 1) or 1
    pool_max = getattr(self.config, "pool_max", 5) or 5
    if pool_max < pool_min:
        pool_max = pool_min
    pool_timeout = getattr(self.config, "pool_timeout", 30.0) or 30.0

    self._engine = create_async_engine(
        url,
        pool_size=pool_min,
        max_overflow=max(0, pool_max - pool_min),
        pool_timeout=pool_timeout,
    )
```

**Step 2:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 3:** `git add` + `git commit -m "feat(sql): MySQLConnector use pool_min/pool_max/pool_timeout"`

---

## Task 3: PostgreSQLConnector 使用 pool 配置

**Files:**
- Modify: `src/datacloud_data/sql_executor/connectors/postgresql_connector.py`

**Step 1:** 与 Task 2 相同逻辑，修改 `_init_engine`：

```python
def _init_engine(self) -> None:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as e:
        raise ImportError(
            "asyncpg not installed. Install with: pip install asyncpg"
        ) from e

    url = _build_sqlalchemy_url(self.config)
    pool_min = getattr(self.config, "pool_min", 1) or 1
    pool_max = getattr(self.config, "pool_max", 5) or 5
    if pool_max < pool_min:
        pool_max = pool_min
    pool_timeout = getattr(self.config, "pool_timeout", 30.0) or 30.0

    self._engine = create_async_engine(
        url,
        pool_size=pool_min,
        max_overflow=max(0, pool_max - pool_min),
        pool_timeout=pool_timeout,
    )
```

**Step 2:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 3:** `git add` + `git commit -m "feat(sql): PostgreSQLConnector use pool_min/pool_max/pool_timeout"`

---

## Task 4: 单元测试验证 pool 参数

**Files:**
- Create: `tests/datacloud_data/test_pool_config.py`

**Step 1:** 编写测试，patch `create_async_engine`，验证 MySQLConnector 和 PostgreSQLConnector 传入正确参数

```python
"""连接池配置单元测试。"""
import pytest
from unittest.mock import patch, MagicMock

from datacloud_data.sql_executor.models import DataSourceConfig


def test_mysql_connector_passes_pool_params() -> None:
    config = DataSourceConfig(
        alias="test",
        db_type="MYSQL",
        jdbc_url="mysql+aiomysql://u:p@localhost/db",
        pool_min=2,
        pool_max=10,
        pool_timeout=15.0,
    )
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine",
        MagicMock(),
    ) as mock_create:
        from datacloud_data.sql_executor.connectors.mysql_connector import (
            MySQLConnector,
        )

        MySQLConnector(config)
        mock_create.assert_called_once()
        call_kw = mock_create.call_args[1]
        assert call_kw["pool_size"] == 2
        assert call_kw["max_overflow"] == 8
        assert call_kw["pool_timeout"] == 15.0


def test_mysql_connector_pool_max_less_than_min() -> None:
    config = DataSourceConfig(
        alias="test",
        db_type="MYSQL",
        jdbc_url="mysql+aiomysql://u:p@localhost/db",
        pool_min=5,
        pool_max=2,
    )
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine",
        MagicMock(),
    ) as mock_create:
        from datacloud_data.sql_executor.connectors.mysql_connector import (
            MySQLConnector,
        )

        MySQLConnector(config)
        call_kw = mock_create.call_args[1]
        assert call_kw["pool_size"] == 5
        assert call_kw["max_overflow"] == 0


def test_postgresql_connector_passes_pool_params() -> None:
    config = DataSourceConfig(
        alias="test",
        db_type="POSTGRESQL",
        jdbc_url="postgresql+asyncpg://u:p@localhost/db",
        pool_min=1,
        pool_max=5,
        pool_timeout=30.0,
    )
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine",
        MagicMock(),
    ) as mock_create:
        from datacloud_data.sql_executor.connectors.postgresql_connector import (
            PostgreSQLConnector,
        )

        PostgreSQLConnector(config)
        mock_create.assert_called_once()
        call_kw = mock_create.call_args[1]
        assert call_kw["pool_size"] == 1
        assert call_kw["max_overflow"] == 4
        assert call_kw["pool_timeout"] == 30.0
```

**Step 2:** 运行 `pytest tests/datacloud_data/test_pool_config.py -v`

Expected: PASS（若 MySQL/PostgreSQL 驱动未安装，ConnectorRegistry 可能未注册，需在 patch 前确保能导入；若导入失败可 `@pytest.mark.skipif`）

**Step 3:** `git add` + `git commit -m "test(sql): add pool config unit tests"`

---

## 执行选项

计划已保存至 `docs/plans/2026-03-08-connection-pool-config-implementation.md`。

**两种执行方式：**

1. **Subagent-Driven（本会话）** — 按任务派发子 agent，逐任务评审
2. **Parallel Session（新会话）** — 在新会话中用 executing-plans 批量执行

选哪种？
