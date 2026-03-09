# M2: 生产级数据源 设计文档

> **日期**：2026-03-08
> **状态**：已确认
> **范围**：MySQL + PostgreSQL + ClickHouse 连接器、连接池、yaml 配置、健康检查

---

## 1 连接器架构

| 连接器 | 驱动 | 连接字符串格式 | 说明 |
|--------|------|----------------|------|
| MySQLConnector | aiomysql | `mysql+aiomysql://user:pass@host:port/db` | Doris 复用此连接器 |
| PostgreSQLConnector | asyncpg | `postgresql+asyncpg://user:pass@host:port/db` | |
| ClickHouseConnector | aioch | 无 SQLAlchemy，直接用 aioch.Client | aioch 原生 async |

**实现方式**：
- MySQL / PostgreSQL：用 SQLAlchemy `create_async_engine` + `AsyncSession` 执行 SQL，复用 SQLAlchemy 连接池。
- ClickHouse：用 `aioch` 直接执行 SQL，不依赖 SQLAlchemy。
- ConnectorRegistry 注册：`MYSQL`、`DORIS`、`POSTGRESQL`、`CLICKHOUSE`。

---

## 2 依赖与可选安装

| 数据库 | 包 | 可选依赖组 |
|--------|-----|------------|
| MySQL | aiomysql | 已有 `sql` |
| PostgreSQL | asyncpg | 新增到 `sql` |
| ClickHouse | aioch | 新增 `clickhouse` 可选组 |

**策略**：连接器在导入时 `try/import`，缺失则 ConnectorRegistry 不注册，调用时抛出 `DataSourceUnavailableError`。

---

## 3 连接池

- **MySQL / PostgreSQL**：SQLAlchemy `create_async_engine` 的 `pool_size`、`max_overflow`，从 `DataSourceConfig.pool_min`、`pool_max` 映射。
- **ClickHouse**：aioch 无连接池，按 alias 复用 Client 实例。
- **SQLite**：保持现状，不建池。

---

## 4 配置与 yaml 加载

- **现状**：`settings.datasources` 为 dict，由 `loader.configure(datasource_configs=...)` 传入。
- **扩展**：新增 `datasources_yaml_path`，若配置则从 yaml 加载；支持 `password: "${CRM_DB_PASSWORD}"` 环境变量替换。
- **优先级**：`datasource_configs` 显式传入 > yaml 文件。

---

## 5 健康检查

- **GET /health**：若 `app.state.loader` 存在且配置了 datasources，对每个数据源调用 `test_connection()`，返回 `{"status":"ok","datasources":{"crm_db":"ok","analytics_db":"ok"}}`。
- **超时**：单数据源 3s，超时标为 `"timeout"`。

---

## 6 错误处理

- 连接失败 → `DataSourceUnavailableError(alias)`
- SQL 执行失败 → `SqlExecutionError(datasource_alias, sql, str(e))`
- 驱动未安装 → `DataSourceUnavailableError`，提示安装对应 optional 依赖

---

## 7 测试策略

- **MySQLConnector / PostgreSQLConnector**：用 `testcontainers` 启动容器；若无 Docker 则 `@pytest.mark.skipif` 跳过。
- **ClickHouseConnector**：同上或 mock aioch。
- **单元测试**：mock 连接器，验证 SqlExecutor 正确调用。
