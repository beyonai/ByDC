# datacloud-data 功能清单与开发计划

> **日期**：2026-03-09 | **组织**：按《数据服务详细设计 2.0》架构层级 | **评估**：全新规划

---

## 表 1：总览

| 层级 | 功能数 |
|------|:------:|
| 工程基础 | 4 |
| 接入层 | 5 |
| 工具层 | 6 |
| SDK 核心层 | 5 |
| SDK 本体层 | 7 |
| SDK 计划层 | 10 |
| SDK 执行层 | 18 |
| SDK 聚合层 | 2 |
| SDK 支撑层 | 9 |
| 配置 | 2 |
| 测试 | 6 |
| Phase 2 | 2 |
| **合计** | **76** |

---

## 表 2：完整功能清单

| # | 层级 | 功能项 | 里程碑 |
|---|------|--------|--------|
| 1 | 工程基础 | 双子包目录结构（datacloud_data + datacloud_data_service） | M0 |
| 2 | 工程基础 | pyproject.toml + 可选依赖分组 | M0 |
| 3 | 工程基础 | 异常层次（DatacloudError → Ontology/Plan/Execution/Aggregation） | M0 |
| 4 | 工程基础 | InvocationContext（contextvars 请求上下文） | M0 |
| 5 | 接入层 | FastAPI 应用工厂 + lifespan OntologyLoader 初始化 | M0 |
| 6 | 接入层 | REST POST /api/v1/query 对接 SDK | M0 |
| 7 | 接入层 | MCP tools/list 动态生成 | M0 |
| 8 | 接入层 | MCP tools/call 路由 | M0 |
| 9 | 接入层 | GET /api/v1/skills/package | M0 |
| 10 | 工具层 | ToolRegistry | M0 |
| 11 | 工具层 | ActionToolGenerator | M0 |
| 12 | 工具层 | UnifiedQuery | M0 |
| 13 | 工具层 | ParamMapper | M0 |
| 14 | 工具层 | TermResolver | M0 |
| 15 | 工具层 | ActionExecutor | M0 |
| 16 | SDK 核心 | View 实体 | M0 |
| 17 | SDK 核心 | Object 实体 | M0 |
| 18 | SDK 核心 | Action 实体 | M0 |
| 19 | SDK 核心 | Relation 模型 | M0 |
| 20 | SDK 核心 | SDK 公开 API | M0 |
| 21 | 本体层 | OntologyClass/Field/Relation/Action 模型 | M0 |
| 22 | 本体层 | TermLoader | M0 |
| 23 | 本体层 | OntologyLoader | M0 |
| 24 | 本体层 | get_object/get_view/get_action | M0 |
| 25 | 本体层 | 场景加载 | M0 |
| 26 | 本体层 | objects_registry.json 标准格式 | M0 |
| 27 | 本体层 | 数据源从本体配置（source_config 解析 + alias 去重） | M0 |
| 28 | 计划层 | ObjectViewPayload + ObjectViewBuilder | M0 |
| 29 | 计划层 | BasePlanGenerator + MockPlanGenerator | M0 |
| 30 | 计划层 | LangGraphPlanGenerator | M0 |
| 31 | 计划层 | PlanValidator（步骤引用 + 聚合一致性） | M0 |
| 32 | 计划层 | ExecutionObjectConverter | M0 |
| 33 | 计划层 | DataPermissionRewriter | M0 |
| 34 | 计划层 | camelCase ↔ snake_case 转换 | M0 |
| 35 | 计划层 | PlanValidator SQL 字段引用校验 | M1 |
| 36 | 计划层 | PlanValidator function_id 校验 | M1 |
| 37 | 计划层 | 计划校验失败自动重试 | M3 |
| 38 | 执行层 | Executor 统一调度 | M0 |
| 39 | 执行层 | ApiExecutor | M0 |
| 40 | 执行层 | ScriptExecutor | M0 |
| 41 | 执行层 | BaseSourceConnector + ConnectorRegistry | M0 |
| 42 | 执行层 | SQLiteConnector | M0 |
| 43 | 执行层 | DataSourceManager + jdbc_parser | M0 |
| 44 | 执行层 | SqlExecutor | M0 |
| 45 | 执行层 | ResultConverter | M0 |
| 46 | 执行层 | Object.query / View.query 管线集成 | M0 |
| 47 | 执行层 | MySQLConnector | M2 |
| 48 | 执行层 | PostgreSQLConnector | M2 |
| 49 | 执行层 | ClickHouseConnector | M2 |
| 50 | 执行层 | SQLAlchemy AsyncEngine 连接池 | M2 |
| 51 | 执行层 | sql_executor_adapter（internal/external） | M2 |
| 52 | 执行层 | DataSourceConfig 从 settings.yaml 加载 | M2 |
| 53 | 执行层 | 连接器健康检查 | M2 |
| 54 | 执行层 | source_type=KNOWLEDGE_BASE + KnowledgeBaseConnector | M4 |
| 55 | 执行层 | PlanStep type=KB + KB 结果 → CSV | M4 |
| 56 | 聚合层 | DirectAggregator | M0 |
| 57 | 聚合层 | SqliteAggregator | M0 |
| 58 | 支撑层 | EventBus | M0 |
| 59 | 支撑层 | 11 种事件类型 | M0 |
| 60 | 支撑层 | TracingMiddleware + EventSpan | M0 |
| 61 | 支撑层 | QueryObserver | M0 |
| 62 | 支撑层 | CsvStorageManager | M0 |
| 63 | 支撑层 | handlers.py 事件处理链注册 | M1 |
| 64 | 支撑层 | 请求级性能日志 | M3 |
| 65 | 支撑层 | OpenTelemetry Span 集成 | M6 |
| 66 | 支撑层 | Grafana Dashboard 模板 | M6 |
| 67 | 配置 | Settings | M0 |
| 68 | 配置 | sql_execution_mode 切换 | M1 |
| 69 | 测试 | SDK 单元测试（78 个） | M0 |
| 70 | 测试 | 本体加载集成测试 | M0 |
| 71 | 测试 | 查询管线集成测试 | M0 |
| 72 | 测试 | REST /query 集成测试 | M0 |
| 73 | 测试 | MCP tools/call 操作类专项测试 | M1 |
| 74 | 测试 | CRM 端到端场景测试（5 个） | M1 |
| 75 | Phase 2 | Skill 包格式定义 | M5 |
| 76 | Phase 2 | Skill 包按 view_id/object_ids 过滤 | M5 |

---

## 表 3：开发里程碑时间线

| 里程碑 | 内容 | 功能编号 | 周期 |
|--------|------|---------|:----:|
| M0 | 核心能力（工程 + 接入 + 工具 + SDK 全层 + 配置 + 基础测试） | #1-34, #38-62, #67, #69-72 | 4 周 |
| M1 | Phase 1 收尾（PlanValidator 增强 + handlers + 测试 + sql_execution_mode） | #35, #36, #63, #68, #73, #74 | 1 周 |
| M2 | 生产级数据源 | #47-53 | 1 周 |
| M3 | 可观测性 v1 | #37, #63, #64 | 1 周 |
| M4 | 知识库 | #54, #55 | 2 周 |
| M5 | Skills API | #75, #76 | 1 周 |
| M6 | 可观测性 v2 | #65, #66 | 1 周 |

**总预估**：M0 约 4 周（核心能力），M1–M3 约 3 周（生产可用），M4–M6 约 4 周（完整能力）。

---

## 表 4：层级-目录-功能对应

| 层级 | 目录 | 功能编号 |
|------|------|---------|
| 工程基础 | - | 1-4 |
| 接入层 | api/ | 5-9 |
| 工具层 | tools/ | 10-15 |
| SDK 核心层 | view.py, object.py, action.py, relation.py | 16-20 |
| SDK 本体层 | ontology/ | 21-27 |
| SDK 计划层 | plan/ | 28-37 |
| SDK 执行层 | executor/, sql_executor/ | 38-55 |
| SDK 聚合层 | aggregator/ | 56-57 |
| SDK 支撑层 | events/, csv_storage/ | 58-66 |
| 配置 | config.py | 67-68 |
| 测试 | tests/ | 69-76 |
