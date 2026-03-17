# datacloud-data 功能清单与开发路线图

> **日期**：2026-03-08
> **状态**：已确认
> **范围**：Phase 1 完整回顾 + Phase 2 扩展规划
> **组织方式**：阶段 + 模块矩阵

---

## 目录

1. [总览](#1-总览)
2. [Phase 1：核心查询管线](#2-phase-1核心查询管线)
3. [Phase 2：扩展能力](#3-phase-2扩展能力)
4. [开发里程碑时间线](#4-开发里程碑时间线)
5. [Phase 1 待完成项详细设计](#5-phase-1-待完成项详细设计)

---

## 1 总览

| 阶段 | 功能项数 | 已完成 | 待完成 |
|------|---------|--------|--------|
| Phase 1 | 60 | 50 | 10 |
| Phase 2 | 19 | 0 | 19 |
| **合计** | **79** | **50** | **29** |

---

## 2 Phase 1：核心查询管线

### P1.0 工程基础

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 1 | 双子包目录结构（`datacloud_data` + `datacloud_data_service`） | 工程 | ✅ |
| 2 | `pyproject.toml` + 可选依赖分组（langchain/sql/service/dev） | 工程 | ✅ |
| 3 | 异常层次（`DatacloudError` → Ontology/Plan/Execution/Aggregation） | SDK | ✅ |
| 4 | `InvocationContext`（contextvars 请求上下文） | SDK | ✅ |

### P1.1 本体层

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 5 | 本体内部模型（OntologyClass/Field/Action/Relation + script 字段） | 本体 | ✅ |
| 6 | 术语加载器（TermLoader：code/label/alias 匹配） | 本体 | ✅ |
| 7 | OntologyLoader（标准 JSON 解析 + configure 注入） | 本体 | ✅ |
| 8 | 核心实体 Object + Action + Relation + get_object() | 本体 | ✅ |
| 9 | View 实体 + get_view() + 场景加载 | 本体 | ✅ |
| 10 | get_action(object_code, action_code) | 本体 | ✅ |
| 11 | objects_registry.json 标准格式迁移 | 本体 | ✅ |
| 12 | SDK 公开 API（`__init__.py` 导出核心类型） | SDK | ✅ |

### P1.2 计划层

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 13 | ObjectViewPayload 模型 + ObjectViewBuilder | 计划 | ✅ |
| 14 | PlanValidator（步骤引用 + 聚合一致性校验） | 计划 | ✅ |
| 15 | BasePlanGenerator + MockPlanGenerator | 计划 | ✅ |
| 16 | LangGraphPlanGenerator（LLM Prompt + JSON 解析 + 重试） | 计划 | ✅ |
| 17 | ExecutionObjectConverter（PlanStep → ExecTask） | 计划 | ✅ |
| 18 | DataPermissionRewriter（tenant_id 注入 SQL WHERE） | 计划 | ✅ |
| 19 | camelCase ↔ snake_case 双向转换 | 计划 | ✅ |
| 20 | PlanValidator SQL 字段引用校验 | 计划 | ⬜ |
| 21 | PlanValidator function_id 存在性校验 | 计划 | ⬜ |

### P1.3 执行层与聚合层

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 22 | BaseSourceConnector + ConnectorRegistry | SQL执行 | ✅ |
| 23 | SQLiteConnector | SQL执行 | ✅ |
| 24 | DataSourceManager + jdbc_parser | SQL执行 | ✅ |
| 25 | SqlExecutor（占位符填充 + bind_from_step + CSV 输出） | SQL执行 | ✅ |
| 26 | ResultConverter（records → CSV） | SQL执行 | ✅ |
| 27 | ApiExecutor（httpx + Header 注入 + CSV 输出） | 执行 | ✅ |
| 28 | ScriptExecutor（compile + 沙箱 + timeout） | 执行 | ✅ |
| 29 | Executor 统一调度（SQL/API/Script 分发） | 执行 | ✅ |
| 30 | Action.execute() 分发（script > API > ActionNotConfiguredError） | 执行 | ✅ |
| 31 | DirectAggregator + SqliteAggregator | 聚合 | ✅ |
| 32 | CsvStorageManager + query 后清理 | 存储 | ✅ |
| 33 | Object.query() 完整管线集成 | 执行 | ✅ |
| 34 | View.query() 跨对象查询管线 | 执行 | ✅ |
| 35 | MySQLConnector（mysql+aiomysql） | SQL执行 | ⬜ |
| 36 | PostgreSQLConnector（postgresql+asyncpg） | SQL执行 | ⬜ |
| 37 | ClickHouseConnector（clickhouse+asynch） | SQL执行 | ⬜ |
| 38 | SQLAlchemy AsyncEngine 连接池（connection_pool.py） | SQL执行 | ⬜ |

### P1.3.5 事件驱动层

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 39 | EventBus（内存同步发布/订阅） | 事件 | ✅ |
| 40 | 11 种事件类型定义 | 事件 | ✅ |
| 41 | TracingMiddleware + EventSpan | 事件 | ✅ |
| 42 | QueryObserver（查询链路可观测性） | 事件 | ✅ |
| 43 | handlers.py（事件处理链注册） | 事件 | ⬜ |

### P1.4 服务层

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 44 | Settings（pydantic-settings + .env） | 服务 | ✅ |
| 45 | FastAPI 应用工厂 + lifespan OntologyLoader 初始化 | 服务 | ✅ |
| 46 | MCP tools/list 动态生成（unified_data_query + action 工具） | 服务 | ✅ |
| 47 | MCP tools/call 路由（UnifiedQuery + ActionExecutor） | 服务 | ✅ |
| 48 | REST POST /api/v1/query 对接 SDK | 服务 | ✅ |
| 49 | ToolRegistry + ActionToolGenerator | 服务 | ✅ |
| 50 | ParamMapper（别名 → param_code） | 服务 | ✅ |
| 51 | TermResolver（标签 → code） | 服务 | ✅ |
| 52 | ActionExecutor（参数流水线 + SDK 调用） | 服务 | ✅ |
| 53 | UnifiedQuery（View.query / Object.query 封装） | 服务 | ✅ |

### P1.5 测试与验收

| # | 功能项 | 模块 | 状态 |
|---|--------|------|------|
| 54 | SDK 单元测试（78 个，全部通过） | 测试 | ✅ |
| 55 | 本体加载集成测试（CRM objects_registry） | 测试 | ✅ |
| 56 | 查询管线集成测试（MockPlanGenerator + SQLite） | 测试 | ✅ |
| 57 | REST /query 集成测试 | 测试 | ✅ |
| 58 | MCP tools/call 操作类工具专项测试 | 测试 | ⬜ |
| 59 | CRM 端到端场景测试（5 个核心场景） | 测试 | ⬜ |
| 60 | sql_execution_mode 切换（internal/external） | 服务 | ⬜ |

---

## 3 Phase 2：扩展能力

### P2.0 生产级数据源

| # | 功能项 | 模块 | 说明 |
|---|--------|------|------|
| 61 | MySQLConnector（mysql+aiomysql） | SQL执行 | Doris 复用此连接器 |
| 62 | PostgreSQLConnector（postgresql+asyncpg） | SQL执行 | |
| 63 | ClickHouseConnector（clickhouse+asynch） | SQL执行 | |
| 64 | SQLAlchemy AsyncEngine 连接池 | SQL执行 | max_size/timeout 可配 |
| 65 | sql_executor_adapter（internal/external 切换） | SQL执行 | external 模式调外部服务 |
| 66 | DataSourceConfig 从 settings.yaml 加载 | 配置 | 支持 `${ENV_VAR}` 密码替换 |
| 67 | 连接器健康检查（test_connection） | SQL执行 | /health 端点聚合 |

### P2.1 知识库与高级数据源

| # | 功能项 | 模块 | 说明 |
|---|--------|------|------|
| 68 | source_type=KNOWLEDGE_BASE 支持 | 本体 | OntologyClass 新增类型 |
| 69 | KnowledgeBaseConnector | 执行 | 向量检索 / RAG 集成 |
| 70 | PlanStep type=KB 支持 | 计划 | LLM 生成 KB 查询步骤 |
| 71 | KB 查询结果 → CSV / records 转换 | 执行 | |

### P2.2 Skills API

| # | 功能项 | 模块 | 说明 |
|---|--------|------|------|
| 72 | GET /api/v1/skills/package | 服务 | 生成 Skill 包供 AI 消费 |
| 73 | Skill 包格式定义（JSON/YAML） | 服务 | 含工具定义 + 使用示例 |
| 74 | Skill 包按 view_id / object_ids 过滤 | 服务 | |

### P2.3 可观测性增强

| # | 功能项 | 模块 | 说明 |
|---|--------|------|------|
| 75 | handlers.py 事件处理链注册 | 事件 | 事件驱动编排层 |
| 76 | 计划校验失败自动重试（LLM 重试循环） | 计划 | max_retries=2 |
| 77 | OpenTelemetry Span 集成 | 事件 | 替代内存 EventSpan |
| 78 | 查询链路 Grafana Dashboard 模板 | 运维 | 模块耗时面板 |
| 79 | 请求级性能日志（按 request_id 各阶段耗时） | 事件 | |

---

## 4 开发里程碑时间线

| 里程碑 | 内容 | 功能编号 | 建议周期 |
|--------|------|---------|---------|
| **M1: Phase 1 收尾** | PlanValidator 增强 + 事件 handlers + MCP 测试 + e2e 测试 | #20, #21, #43, #58, #59, #60 | 1 周 |
| **M2: 生产级数据源** | MySQL/PG/CH 连接器 + 连接池 + yaml 配置 + 健康检查 | #35-38, #61-67 | 1 周 |
| **M3: 可观测性 v1** | 事件处理链 + 计划重试循环 + 性能日志 | #75, #76, #79 | 1 周 |
| **M4: 知识库** | KB source_type + 连接器 + PlanStep 扩展 | #68-71 | 2 周 |
| **M5: Skills API** | Skill 包格式 + REST 接口 + 过滤 | #72-74 | 1 周 |
| **M6: 可观测性 v2** | OpenTelemetry + Grafana 模板 | #77, #78 | 1 周 |

**总预估**：M1-M3 约 3 周（生产可用），M4-M6 约 4 周（完整能力）。

---

## 5 Phase 1 待完成项详细设计

### 5.1 PlanValidator SQL 字段引用校验（#20）

从 SQL 中正则提取 `SELECT`/`WHERE`/`JOIN ON` 中引用的列名，校验其是否存在于 `ObjectViewPayload.objects[].fields[]`。

```python
def _validate_sql_field_refs(self, step: PlanStep, payload: ObjectViewPayload) -> list[str]:
    """正则提取 SQL 列名，校验是否在 ObjectView 字段中。"""
```

### 5.2 PlanValidator function_id 校验（#21）

校验 API 步骤的 `function_id` 是否存在于 `ObjectViewPayload.objects[].functions[]`。

### 5.3 MySQLConnector / PostgreSQLConnector / ClickHouseConnector（#35-37）

继承 `BaseSourceConnector`，使用 SQLAlchemy AsyncEngine：
- MySQL: `mysql+aiomysql://`
- PostgreSQL: `postgresql+asyncpg://`
- ClickHouse: `clickhouse+asynch://`

在 `ConnectorRegistry` 模块加载时自动注册。

### 5.4 连接池（#38）

`connection_pool.py` 基于 SQLAlchemy `create_async_engine`，配置 `pool_size`、`max_overflow`、`pool_timeout`。

### 5.5 handlers.py 事件处理链（#43）

注册 EventBus 订阅者，将查询管线各阶段事件按顺序串联。当前为可观测性用途，不改变直接调用链路。

### 5.6 MCP tools/call 操作类测试（#58）

测试 action 工具调用完整流水线：ParamMapper → TermResolver → invoke_action。

### 5.7 CRM 端到端场景测试（#59）

5 个核心场景：
1. 自然语言查询「查询邹海天的商机」
2. 跨数据源「邹海天签了合同的商机」
3. 不可回答「按合同金额统计」→ clarification
4. MCP 操作类工具 `query_bo_by_owner`
5. 术语值测试：传"已签约" → "SIGNED"

### 5.8 sql_execution_mode（#60）

Settings 新增 `sql_execution_mode: str = "internal"`。`internal` 用内置 SqlExecutor，`external` 通过 HTTP 调外部 SQL 执行服务。
