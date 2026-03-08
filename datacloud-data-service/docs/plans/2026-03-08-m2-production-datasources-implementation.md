# M2: 生产级数据源 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 MySQL、PostgreSQL、ClickHouse 三个连接器，扩展 jdbc_parser，支持连接池、yaml 配置、健康检查。

**Architecture:** 三个连接器继承 BaseSourceConnector，MySQL/PG 用 SQLAlchemy AsyncEngine，ClickHouse 用 aioch。ConnectorRegistry 按需注册（驱动存在时）。健康检查在 /health 聚合 datasources 的 test_connection。

**Tech Stack:** SQLAlchemy 2.0 async, aiomysql, asyncpg, aioch, PyYAML, testcontainers（可选）

---

## Task 1: 扩展 pyproject.toml 依赖

**Files:** `pyproject.toml`

**Step 1:** 修改 `[project.optional-dependencies]` 的 `sql` 组：

```toml
sql = ["sqlalchemy[asyncio]>=2.0", "aiomysql>=0.2", "aiosqlite>=0.19", "asyncpg>=0.29"]
clickhouse = ["aioch>=0.0.14"]
```

**Step 2:** 运行 `uv sync` 验证依赖安装。

---

## Task 2: 扩展 jdbc_parser 支持 ClickHouse

**Files:** `src/datacloud_data_sdk/sql_executor/jdbc_parser.py`

**Step 1:** 添加 CLICKHOUSE 分支，将 `jdbc:clickhouse://host:port/db` 转为 aioch 所需的 host/port/database 参数（或连接字符串格式）。

**Step 2:** 添加测试 `tests/datacloud_data_sdk/test_jdbc_parser.py` 验证 MySQL、PostgreSQL、ClickHouse URL 解析。

---

## Task 3: MySQLConnector

**Files:**
- Create: `src/datacloud_data_sdk/sql_executor/connectors/mysql_connector.py`
- Modify: `src/datacloud_data_sdk/sql_executor/connector_registry.py`

**Step 1:** 创建 `MySQLConnector`，继承 `BaseSourceConnector`：
- `supported_type()` 返回 `"MYSQL"`
- `__init__` 用 `parse_jdbc_url` 得到 SQLAlchemy URL，`create_async_engine` 创建 engine（pool_size=pool_max）
- `execute(sql, params)` 用 `AsyncSession` 执行 `text(sql)`，params 绑定
- `test_connection()` 执行 `SELECT 1`
- `close()` 调用 `engine.dispose()`

**Step 2:** 在 connector_registry 中 `try/import` MySQLConnector，成功则 `ConnectorRegistry.register("MYSQL", MySQLConnector)` 和 `register("DORIS", MySQLConnector)`。

**Step 3:** 添加单元测试，mock engine 或使用 testcontainers（可选跳过）。

---

## Task 4: PostgreSQLConnector

**Files:**
- Create: `src/datacloud_data_sdk/sql_executor/connectors/postgresql_connector.py`
- Modify: `src/datacloud_data_sdk/sql_executor/connector_registry.py`

**Step 1:** 创建 `PostgreSQLConnector`，与 MySQL 类似，URL 前缀 `postgresql+asyncpg://`。

**Step 2:** 注册 `POSTGRESQL`。

**Step 3:** 添加单元测试。

---

## Task 5: ClickHouseConnector

**Files:**
- Create: `src/datacloud_data_sdk/sql_executor/connectors/clickhouse_connector.py`
- Modify: `src/datacloud_data_sdk/sql_executor/connector_registry.py`

**Step 1:** 创建 `ClickHouseConnector`：
- 从 jdbc_url 解析 host、port、database（或扩展 jdbc_parser 返回 dict）
- 用 `aioch.Client` 连接，`execute(sql)` 返回结果
- 将 aioch 返回格式转为 `list[dict]`

**Step 2:** 注册 `CLICKHOUSE`（需 `try/import aioch`）。

**Step 3:** 添加单元测试，mock aioch.Client。

---

## Task 6: DataSourceConfig 环境变量替换

**Files:**
- Create: `src/datacloud_data_sdk/sql_executor/config_loader.py`
- Modify: `src/datacloud_data_service/config.py`

**Step 1:** 创建 `load_datasources_from_yaml(path)`，解析 yaml，对 `password` 等字段做 `${VAR}` 替换。

**Step 2:** Settings 新增 `datasources_yaml_path: str = ""`，lifespan 中若配置则加载并 merge 到 datasource_configs。

---

## Task 7: /health 聚合数据源健康检查

**Files:** `src/datacloud_data_service/api/routes.py`

**Step 1:** 修改 `/health` 或新增 `@app.get("/health")` 逻辑：若 `app.state.loader` 存在且 `loader._config.datasource_configs` 非空，则对每个 alias 调用 `DataSourceManager.get_connector(alias).test_connection()`，超时 3s，结果写入 `datasources` 字段。

**Step 2:** 添加测试验证 health 返回结构。

---

## 执行顺序

| 顺序 | Task | 预计时间 |
|------|------|---------|
| 1 | Task 1: 依赖 | 5 min |
| 2 | Task 2: jdbc_parser | 10 min |
| 3 | Task 3: MySQLConnector | 20 min |
| 4 | Task 4: PostgreSQLConnector | 15 min |
| 5 | Task 5: ClickHouseConnector | 20 min |
| 6 | Task 6: yaml 配置 | 15 min |
| 7 | Task 7: 健康检查 | 10 min |
