# #38 连接池配置补齐 设计文档

> **日期**：2026-03-08
> **状态**：已确认
> **范围**：MySQL / PostgreSQL 连接器 pool 参数可配置

---

## 1 目标与范围

**目标**：使 MySQL / PostgreSQL 连接器的连接池参数可配置，并正确映射到 SQLAlchemy。

**范围**：
- `DataSourceConfig` 新增 `pool_timeout`
- MySQLConnector、PostgreSQLConnector 使用 `pool_min`、`pool_max`、`pool_timeout`
- SQLite、ClickHouse 保持现状，不建池

---

## 2 配置映射

| DataSourceConfig | SQLAlchemy 参数 | 默认值 |
|------------------|-----------------|--------|
| `pool_min`       | `pool_size`     | 1      |
| `pool_max - pool_min` | `max_overflow` | 4 |
| `pool_timeout`   | `pool_timeout`  | 30.0（秒）|

**说明**：SQLAlchemy 的 `pool_size` 为常驻连接数，`max_overflow` 为溢出连接数。总最大连接数 = pool_size + max_overflow。采用 `pool_size = pool_min`、`max_overflow = max(0, pool_max - pool_min)`。

---

## 3 修改点

### 3.1 DataSourceConfig（`models.py`）

- 新增 `pool_timeout: float = 30.0`

### 3.2 MySQLConnector

- 从 config 读取 `pool_min`、`pool_max`、`pool_timeout`
- `create_async_engine` 传入 `pool_size`、`max_overflow`、`pool_timeout`

### 3.3 PostgreSQLConnector

- 与 MySQLConnector 相同逻辑

---

## 4 错误处理

- `pool_max < pool_min` 时，使用 `pool_min` 作为 `pool_max` 并记录 warning，或抛出 `ValueError`。建议：静默修正为 `pool_max = pool_min`，`max_overflow = 0`。

---

## 5 测试

- 单元测试：验证 connector 初始化时 `create_async_engine` 被调用且参数正确（可 mock 或 patch）
- 可选：testcontainers 真实连接验证
