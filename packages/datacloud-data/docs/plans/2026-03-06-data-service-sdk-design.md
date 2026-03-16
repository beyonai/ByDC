# datacloud-data-service & datacloud-data-sdk 实现设计

> **日期**：2026-03-06  
> **状态**：已确认，待实现  
> **范围**：Phase 1 完整实现——OntologyLoader + 查询执行主链路 + MCP 工具层  
> **测试场景**：CRM 销售场景（`objects_registry.json` + `datacloud-mock`）

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [工程结构与包配置](#2-工程结构与包配置)
3. [本体层设计](#3-本体层设计)
4. [计划层设计](#4-计划层设计)
5. [执行层与聚合层设计](#5-执行层与聚合层设计)
6. [服务层设计](#6-服务层设计)
7. [测试策略](#7-测试策略)

---

## 1 背景与目标

### 1.1 目标

基于《数据服务详细设计 2.0》与 `objects_registry.json`（CRM 销售场景本体），实现：

- **A. OntologyLoader + 本体层**：解析 `objects_registry.json` → `OntologyClass/Field/Relation/Action` → 产出 `View/Object` 实例，支持 `get_description()` 和 `get_schema()`
- **B. 查询执行主链路**：`OntologyLoader → ObjectViewPayload → LangGraph QPG → PlanValidator → Executor → Aggregator → records`
- **C. MCP 工具层**：`tools/list` 返回操作类工具（含 inputSchema），`tools/call` 执行并返回结果

### 1.2 选型决策

| 维度 | 决策 |
|------|------|
| **包结构** | 双子包（`datacloud_data_sdk` + `datacloud_data_service`），SDK 开源质量 |
| **LLM 框架** | LangGraph（OpenAI 兼容接口，model/base_url/api_key 可配置） |
| **SQL 执行** | 内置 `SqlExecutor`（SQLAlchemy AsyncIO），支持切换外部模式 |
| **测试场景** | CRM 销售场景，`datacloud-mock` 提供 Mock API + DB |
| **测试策略** | SDK 单元测试 + 服务层测试 + CRM 端到端集成测试 |

### 1.3 四个交付阶段

| 阶段 | 内容 | 可测试输出 |
|------|------|-----------|
| **P1.1** | 本体层：OntologyLoader + View/Object/Action | `get_description()`、`get_schema()` 单测通过 |
| **P1.2** | 计划层：ObjectViewPayload + LangGraph QPG + Validator | 给定问题 → 返回 `QueryExecutionPlan` |
| **P1.3** | 执行层：ApiExecutor + SqlExecutor + Aggregator | 给定 Plan → 返回 `records` |
| **P1.4** | 服务层：FastAPI + MCP tools/list + tools/call | HTTP 接口可调用 |

---

## 2 工程结构与包配置

### 2.1 目录树

```
datacloud-data-service/
├── resources/
│   └── ontology/
│       └── crm_demo/                   # 从 datacloud-mock 复用
│           ├── objects_registry.json
│           └── scene_01_data_analysis.json
├── src/
│   ├── datacloud_data_sdk/             # SDK 子包（核心逻辑，零 FastAPI 依赖）
│   │   ├── __init__.py                 # 公开 API 面（OntologyLoader, View, Object, ...）
│   │   ├── context.py                  # InvocationContext（contextvars）
│   │   ├── view.py                     # View 实体
│   │   ├── object.py                   # Object 实体
│   │   ├── action.py                   # Action 实体
│   │   ├── relation.py                 # Relation 模型
│   │   ├── exceptions.py               # 结构化错误层次
│   │   ├── ontology/                   # 本体层
│   │   │   ├── __init__.py
│   │   │   ├── models.py               # OntologyClass/Field/Relation/Action/ActionParam
│   │   │   ├── loader.py               # OntologyLoader（本体层 API + 核心层 API）
│   │   │   └── term_loader.py          # 术语集加载
│   │   ├── plan/                       # 计划层
│   │   │   ├── __init__.py
│   │   │   ├── models.py               # ObjectViewPayload, QueryExecutionPlan, PlanStep, ...
│   │   │   ├── object_view_builder.py  # OntologyLoader → ObjectViewPayload
│   │   │   ├── query_plan_generator.py # BasePlanGenerator + LangGraphPlanGenerator
│   │   │   ├── plan_validator.py       # 计划校验
│   │   │   ├── data_permission_rewriter.py
│   │   │   └── execution_object_converter.py
│   │   ├── executor/                   # 执行层
│   │   │   ├── __init__.py
│   │   │   ├── executor.py             # 调度 API/SQL 步骤
│   │   │   ├── api_executor.py         # httpx 异步 API 调用
│   │   │   └── sql_executor_adapter.py # 内置/外部 SQL 执行切换
│   │   ├── sql_executor/               # DB 连接与 SQL 执行
│   │   │   ├── __init__.py
│   │   │   ├── models.py               # SqlExecTask, DataSourceConfig
│   │   │   ├── data_source_manager.py
│   │   │   ├── connection_pool.py      # SQLAlchemy AsyncEngine
│   │   │   ├── sql_executor.py
│   │   │   ├── result_converter.py     # ResultSet → CSV
│   │   │   └── jdbc_parser.py          # JDBC URL → SQLAlchemy URL
│   │   ├── aggregator/                 # 聚合层
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # BaseAggregator (ABC)
│   │   │   ├── direct_aggregator.py    # strategy=DIRECT
│   │   │   └── sqlite_aggregator.py    # strategy=SQLITE_MEM
│   │   ├── events/                     # 事件总线（内存同步，MVP）
│   │   │   ├── __init__.py
│   │   │   ├── bus.py
│   │   │   ├── events.py
│   │   │   ├── handlers.py
│   │   │   └── tracing.py
│   │   └── csv_storage/                # CSV 暂存管理
│   │       ├── __init__.py
│   │       └── manager.py
│   │
│   └── datacloud_data_service/         # Service 子包（薄接入层）
│       ├── __init__.py
│       ├── config.py                   # Settings（pydantic-settings）
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py               # FastAPI 路由注册
│       │   ├── query.py                # POST /api/v1/query
│       │   ├── mcp_handler.py          # POST /api/v1/mcp（JSON-RPC 2.0）
│       │   └── skills.py               # GET /api/v1/skills/package（Phase 2）
│       └── tools/
│           ├── __init__.py
│           ├── registry.py             # 工具注册与列表
│           ├── unified_query.py        # unified_data_query 工具封装
│           ├── action_tool_generator.py
│           ├── action_executor.py      # 参数流水线 + 调用 SDK
│           ├── param_mapper.py         # 逻辑名映射 + mapping_path 写入
│           └── term_resolver.py        # 术语标签 → 标准 code
│
├── tests/
│   ├── datacloud_data_sdk/
│   │   ├── test_ontology_loader.py
│   │   ├── test_object_view_builder.py
│   │   ├── test_plan_validator.py
│   │   ├── test_execution_object_converter.py
│   │   ├── test_api_executor.py
│   │   ├── test_sql_executor.py
│   │   ├── test_aggregator.py
│   │   └── integration/
│   │       ├── test_ontology_loader_integration.py
│   │       └── test_query_pipeline_integration.py
│   ├── datacloud_data_service/
│   │   ├── test_mcp_tools_list.py
│   │   ├── test_mcp_tools_call_action.py
│   │   └── test_rest_query.py
│   └── e2e/
│       └── test_crm_scenarios.py
└── pyproject.toml
```

### 2.2 pyproject.toml 关键变化

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/datacloud_data_sdk", "src/datacloud_data_service"]

[project.optional-dependencies]
langchain = ["langgraph>=0.2", "langchain-openai>=0.1"]
sql       = ["sqlalchemy[asyncio]>=2.0", "aiomysql>=0.2", "pymysql>=1.0"]
all       = ["datacloud-data-service[langchain,sql]"]
dev       = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-mock>=3.0", "httpx>=0.27"]
```

---

## 3 本体层设计

### 3.1 内部模型（ontology/models.py）

```python
@dataclass
class FieldPhysicalMapping:
    source_type: str          # DB / API
    source_ref: str           # DB 列名 或 API 参数路径（$.response.boName）
    datasource_alias: str     # 对应数据源 alias

@dataclass
class OntologyField:
    field_code: str
    field_name: str
    field_type: str            # STRING / NUMBER / DATE / BOOLEAN / INTEGER 等
    description: str = ""     # 字段业务含义
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    term_set: str | None = None          # 术语集 ID（如 stage_code → 商机阶段术语集）
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)

@dataclass
class OntologyActionParam:
    param_code: str
    param_name: str
    direction: str             # IN / OUT / INOUT
    param_type: str
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""    # $.requestBody.xxx 或 $.parameters.xxx
    term_set: str | None = None

@dataclass
class OntologyAction:
    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]  # → functions[].function_code

@dataclass
class OntologyRelation:
    relation_code: str
    source_class: str
    target_class: str
    relation_type: str         # hasMany / belongsTo / oneToMany / manyToMany
    join_keys: list[dict]      # [{from_field, to_field}]
    description: str = ""

@dataclass
class OntologyClass:
    object_code: str
    object_name: str
    description: str
    source_type: str           # DB / API
    datasource_alias: str | None = None   # 引用外部 DataSourceConfig（方案 A）
    table_name: str | None = None
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)
```

### 3.2 OntologyLoader API（ontology/loader.py）

```python
class OntologyLoader:
    # 加载方式
    def load_from_path(self, path: str | Path) -> None
    def load_from_content(self, content: dict, format: str = "json") -> None

    # 本体层 API（返回内部模型）
    def get_ontology_class(self, object_code: str) -> OntologyClass        # 抛 ObjectNotFoundError
    def get_ontology_classes(self, object_ids: list[str] | None = None) -> list[OntologyClass]
    def get_ontology_relations(self) -> list[OntologyRelation]
    def get_function_config(self, function_code: str) -> dict              # 原始 api_schema

    # 核心层 API（返回 View / Object / Action 实例）
    def get_object(self, object_code: str) -> Object
    def get_view(self, view_id: str) -> View                               # 从 scene_XX.json
    def get_action(self, object_code: str, action_code: str) -> Action
```

### 3.3 核心实体公开方法

**Object（object.py）**

| 方法 | 返回 | 说明 |
|------|------|------|
| `query(question)` | `QueryResult` | 自然语言查询（走完整计划链路） |
| `get_description()` | `str`（Markdown） | 字段、别名、动作出入参、关联对象 |
| `invoke_action(action_code, params)` | `ActionResult` | 执行操作类动作 |
| `get_action_schema(action_code)` | `dict` | `{input: JSON Schema, output: JSON Schema}` |
| `get_relations()` | `list[Relation]` | 该对象参与的所有关联 |
| `list_action_codes()` | `list[str]` | 所有可用动作编码 |

**View（view.py）**

| 方法 | 返回 | 说明 |
|------|------|------|
| `query(question)` | `QueryResult` | 跨对象自然语言查询 |
| `get_description()` | `str`（Markdown） | 视图包含对象、关联、可用动作 |
| `invoke_object_action(object_id, action_code, params)` | `ActionResult` | 通过视图调用对象动作 |

**Action（action.py）**

| 方法 | 返回 | 说明 |
|------|------|------|
| `execute(params)` | `ActionResult` | 执行动作（调用 ApiExecutor） |
| `get_schema()` | `dict` | `{input: {...}, output: {...}}` JSON Schema |

### 3.4 get_description() Markdown 示例

```markdown
## 对象：销售商机（sales_business_opportunity）

**数据来源**：CRM 数据库（crm_db），表 `sales_business_opportunity`

**字段**：
- bo_id（商机ID, string）—— 商机唯一标识
- bo_name（商机名称/项目名称, string）—— 商机的标题或项目名称
- owner_id（负责人ID, string）
- stage_code（阶段/商机阶段, string）—— 商机当前所处销售阶段（术语集：bo_stage）

**动作**：
- `query_bo_by_owner`：按负责人查商机，入参：owner_id(string, 必填)，返回：bo_id, bo_name, stage_code

**关联**：
- 关联 销售合同（sales_contract），通过 bo_id 连接，ONE_TO_MANY —— 一个商机可签署多份合同
```

### 3.5 开源质量约束

- **公开 API 面**：`datacloud_data_sdk/__init__.py` 仅暴露 `OntologyLoader`、`View`、`Object`、`Action`、`Relation`、`InvocationContext`、`DatacloudError` 及子类
- **可选依赖**：核心本体层零依赖；LangGraph / SQL 驱动为可选 extras
- **抽象接口**：`BasePlanGenerator(ABC)`、`BaseAggregator(ABC)` 允许替换实现
- **全量类型注解** + **异步优先**（所有 I/O 均为 `async/await`）

### 3.6 错误层次（exceptions.py）

```
DatacloudError（基类）
├── OntologyError
│   ├── ObjectNotFoundError(object_code)
│   ├── ActionNotFoundError(object_code, action_code)
│   └── InvalidOntologyFormatError(path, reason)
├── PlanError
│   ├── PlanGenerationError(question, cause)
│   ├── PlanValidationError(errors: list[str])
│   └── CannotAnswerError(clarification)
├── ExecutionError
│   ├── ApiExecutionError(function_code, status_code, body)
│   ├── SqlExecutionError(datasource_alias, sql, cause)
│   └── DataSourceUnavailableError(alias)
└── AggregationError(strategy, sql, cause)
```

---

## 4 计划层设计

### 4.1 ObjectViewPayload 模型（plan/models.py）

```python
@dataclass
class ObjectViewSource:
    source_id: str
    source_type: str           # DB / API
    datasource_alias: str | None = None

@dataclass
class ObjectViewField:
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""

@dataclass
class ObjectViewObject:
    object_id: str
    object_name: str           # 中文名（如"销售商机"）
    description: str = ""
    source_id: str = ""
    table: str | None = None
    fields: list[ObjectViewField] = field(default_factory=list)
    functions: list[dict] = field(default_factory=list)

@dataclass
class ObjectViewRelation:
    from_object: str
    to_object: str
    cardinality: str
    join_keys: list[dict]
    description: str = ""     # 业务含义（如"一个商机可签署多份合同"）

@dataclass
class ObjectViewPayload:
    view_id: str
    view_name: str = ""
    description: str = ""
    sources: list[ObjectViewSource] = field(default_factory=list)
    objects: list[ObjectViewObject] = field(default_factory=list)
    relations: list[ObjectViewRelation] = field(default_factory=list)
```

### 4.2 QueryExecutionPlan 模型

```python
@dataclass
class PlanStep:
    step_id: str
    type: str                  # SQL / API
    source_id: str
    datasource_alias: str | None = None
    sql_template: str | None = None
    bind_from_step: str | None = None
    bind_key: str | None = None
    function_id: str | None = None
    params: dict = field(default_factory=dict)
    output_ref: str = ""
    csv_table_name: str | None = None

@dataclass
class PlanAggregation:
    strategy: str              # DIRECT / SQLITE_MEM
    final_step_id: str | None = None
    sqlite_sql: str | None = None
    columns: list[dict] = field(default_factory=list)

@dataclass
class QueryExecutionPlan:
    question: str
    can_answer: bool
    clarification: str | None = None
    steps: list[PlanStep] = field(default_factory=list)
    aggregation: PlanAggregation | None = None
```

### 4.3 LangGraph QueryPlanGenerator

使用 LangGraph 构建**单节点图**（MVP），可扩展为多节点重试图：

- **State**：`{ object_view, question, validation_errors?, retry_count }`
- **Node: call_llm**：构造 Prompt（ObjectViewPayload JSON + 问题 + 可选 validationErrors） → 调用 LLM → 解析 JSON → `QueryExecutionPlan`
- **Prompt 模板**：来自《数据服务详细设计 2.0》§6.6，注入点 `{{objectView}}`、`{{question}}`、`{{validationErrors}}`
- **可替换**：通过 `BasePlanGenerator(ABC)` 抽象，测试时注入 `MockPlanGenerator`

### 4.4 PlanValidator 校验规则

| 校验类型 | 规则 |
|---------|------|
| 步骤引用 | `sourceId`、`functionId` 必须在 ObjectViewPayload 中存在 |
| 字段引用 | SQL 引用字段（正则提取）必须在对应 object.fields 中 |
| 聚合一致性 | DIRECT → `finalStepId` 存在；SQLITE_MEM → steps 均有 `csvTableName` |
| 必填项 | `canAnswer=true` 时 steps 非空，aggregation 非 null |

### 4.5 DataPermissionRewriter

从 `InvocationContext` 注入 `tenant_id` 过滤条件到 SQL WHERE 子句。MVP 阶段仅注入 `tenant_id`，后续可扩展行级权限。

### 4.6 ExecutionObjectConverter

将 `PlanStep` 转为 `ApiExecTask` 或 `SqlExecTask`，供执行层直接消费。

---

## 5 执行层与聚合层设计

### 5.1 执行任务模型

```python
@dataclass
class ApiExecTask:
    function_code: str
    params: dict
    output_ref: str
    csv_table_name: str | None = None

@dataclass
class SqlExecTask:
    datasource_alias: str
    sql_template: str
    bind_from_step: str | None = None
    bind_key: str | None = None
    output_ref: str = ""
    csv_table_name: str | None = None
```

### 5.2 ApiExecutor

- 从 `OntologyLoader.get_function_config(function_code)` 取 OpenAPI `api_schema`
- 解析 `servers[0].url` + `paths` 得到完整 URL 与 HTTP method
- 从 `InvocationContext` 注入 `Authorization`、`X-Tenant-Id` 等 Header
- 使用 `httpx.AsyncClient`，超时 30s
- 响应按 OUT params 的 `mapping_path` 提取数据 → 写 CSV

### 5.3 SqlExecutor 模块（含可扩展连接器设计）

```
sql_executor/
├── models.py               # SqlExecTask, DataSourceConfig
├── base_connector.py       # BaseSourceConnector(ABC)：统一数据源接口
├── connector_registry.py   # ConnectorRegistry：type → 实现类，支持注册自定义
├── connectors/
│   ├── mysql_connector.py      # MYSQL / DORIS（mysql+aiomysql://）
│   ├── postgresql_connector.py # POSTGRESQL（postgresql+asyncpg://）
│   ├── clickhouse_connector.py # CLICKHOUSE（clickhouse+asynch://）
│   └── sqlite_connector.py     # SQLITE（本地测试用）
├── data_source_manager.py  # 按 alias 查找 DataSourceConfig，懒加载连接器
├── jdbc_parser.py          # jdbc:mysql://... → SQLAlchemy URL
├── sql_executor.py         # 占位符填充 → ConnectorRegistry.get(type).execute()
└── result_converter.py     # ResultSet → CSV（支持分批写入）
```

**BaseSourceConnector（base_connector.py）**：

```python
class BaseSourceConnector(ABC):
    def __init__(self, config: DataSourceConfig) -> None: ...

    @abstractmethod
    async def execute(self, sql: str, params: dict | None = None) -> list[dict]: ...

    @abstractmethod
    async def test_connection(self) -> bool: ...

    @classmethod
    @abstractmethod
    def supported_type(cls) -> str: ...    # "MYSQL" / "POSTGRESQL" / "CLICKHOUSE" 等
```

**ConnectorRegistry（connector_registry.py）**：

```python
class ConnectorRegistry:
    _registry: dict[str, type[BaseSourceConnector]] = {}

    @classmethod
    def register(cls, db_type: str, connector_cls: type[BaseSourceConnector]) -> None:
        cls._registry[db_type.upper()] = connector_cls

    @classmethod
    def get(cls, db_type: str) -> type[BaseSourceConnector]:
        if db_type.upper() not in cls._registry:
            raise DataSourceUnavailableError(f"Unsupported datasource type: {db_type}")
        return cls._registry[db_type.upper()]

# 内置注册（模块加载时执行）
ConnectorRegistry.register("MYSQL", MySQLConnector)
ConnectorRegistry.register("DORIS", MySQLConnector)      # Doris 兼容 MySQL 协议
ConnectorRegistry.register("POSTGRESQL", PostgreSQLConnector)
ConnectorRegistry.register("CLICKHOUSE", ClickHouseConnector)
ConnectorRegistry.register("SQLITE", SQLiteConnector)

# 使用者注册自定义连接器（开放扩展）
# ConnectorRegistry.register("BIGQUERY", MyBigQueryConnector)
```

**数据源类型映射**：

| type | 默认连接器 | SQLAlchemy URL 前缀 |
|------|-----------|-------------------|
| MYSQL | `MySQLConnector` | `mysql+aiomysql://` |
| DORIS | `MySQLConnector`（兼容） | `mysql+aiomysql://` |
| POSTGRESQL | `PostgreSQLConnector` | `postgresql+asyncpg://` |
| CLICKHOUSE | `ClickHouseConnector` | `clickhouse+asynch://` |
| SQLITE | `SQLiteConnector` | `sqlite+aiosqlite://` |
| 自定义 | `ConnectorRegistry.get(type)` | 实现方自定义 |

**DataSourceConfig 来自 `settings.yaml`（不内嵌于本体文件）**：

```yaml
datasources:
  crm_db:
    type: MYSQL
    jdbc_url: "jdbc:mysql://mysql:3306/crm_demo"
    user: "readonly"
    password: "${CRM_DB_PASSWORD}"
    pool:
      max_size: 10
      timeout: 3000
```

### 5.4 聚合层

**DirectAggregator**：读取 `finalStepId` 对应 CSV，按 `columns` 过滤重命名，返回 `list[dict]`。

**SqliteAggregator**：创建 SQLite `:memory:` 连接 → 各 step CSV 按 `csvTableName` 导入 → 执行 `sqliteSql` → 返回 records → 连接即销即毁。

两者均实现 `BaseAggregator(ABC)`，通过工厂方法按 `strategy` 选择。

### 5.5 错误处理

| 场景 | 错误类型 |
|------|---------|
| API 超时/4xx/5xx | `ApiExecutionError(function_code, status_code, body)` |
| SQL 执行失败 | `SqlExecutionError(datasource_alias, sql, cause)` |
| 连接池耗尽 | `DataSourceUnavailableError(alias)` |
| bind_from_step CSV 缺失 | `StepDependencyError(step_id, depends_on)` |
| SQLite 聚合 SQL 错误 | `AggregationError(strategy, sql, cause)` |

---

## 6 服务层设计

### 6.1 设计原则

服务层是 SDK 的**薄接入壳**，只做三件事：
1. 解析 HTTP Header → 设置 `InvocationContext`
2. 按工具类型分流（统一查询 vs 操作类工具）
3. 格式化 SDK 返回结果为 MCP/REST 响应

**所有业务逻辑在 SDK 内，服务层不含核心逻辑。**

### 6.2 请求分流（mcp_handler.py）

```
tools/list → ToolRegistry.list_tools(view_id, object_ids)
           → [unified_data_query] + [action tools]

tools/call(unified_data_query, {question}) → View.query(question)
tools/call(<action_code>, {arguments})     → ActionExecutor.execute(action_code, arguments)

POST /api/v1/query → View.query(question)
```

### 6.3 操作类工具执行流水线（action_executor.py）

```
arguments
  → ParamMapper.map_names()       # 别名 → param_code
  → TermResolver.resolve()        # 标签 → 标准 code；失败 → TermResolutionError
  → ParamMapper.map_to_physical() # mapping_path → API body/query/path
  → Object.invoke_action()        # SDK 执行
  → 格式化为 MCP content
```

### 6.4 InvocationContext 设置（每次请求入口）

```python
with InvocationContext(
    tenant_id   = request.headers["X-Tenant-Id"],
    user_id     = request.headers["X-User-Id"],
    session_id  = request.headers["X-Session-Id"],
    token       = request.headers["Authorization"].removeprefix("Bearer "),
    system_code = request.headers["X-System-Code"],
):
    return await process(request)
```

### 6.5 REST 接口清单

| 文件 | 接口 | 说明 |
|------|------|------|
| `query.py` | `POST /api/v1/query` | 统一数据查询 |
| `mcp_handler.py` | `POST /api/v1/mcp` | MCP JSON-RPC 2.0 |
| `skills.py` | `GET /api/v1/skills/package` | Skill 包生成（Phase 2） |

### 6.6 配置（config.py）

```python
class Settings(BaseSettings):
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str
    llm_model: str = "gpt-4o"
    datasources: dict[str, DataSourceConfig] = {}
    ontology_path: str = "resources/ontology"
    sql_execution_mode: str = "internal"   # internal / external

    class Config:
        env_file = ".env"
```

---

## 7 测试策略

### 7.1 测试分层

| 层级 | 目录 | 工具 | 外部依赖 |
|------|------|------|---------|
| SDK 单元测试 | `tests/datacloud_data_sdk/` | pytest + pytest-mock | 无 |
| SDK 集成测试 | `tests/datacloud_data_sdk/integration/` | pytest-asyncio | 仅本地文件 |
| 服务层测试 | `tests/datacloud_data_service/` | httpx TestClient + Mock SDK | 无 |
| CRM 端到端 | `tests/e2e/` | pytest-asyncio | datacloud-mock 服务 |

### 7.2 SDK 单元测试核心用例

**本体层**

| 测试 | 验证点 |
|------|-------|
| `test_load_objects_registry_json` | `sales_business_opportunity` 解析为 `OntologyClass`，fields/actions/relations 数量正确 |
| `test_get_object_returns_instance` | `get_object()` 返回 `Object` 实例 |
| `test_get_description_contains_fields` | Markdown 含字段名和别名 |
| `test_get_action_schema` | 返回合法 JSON Schema，required 字段正确 |
| `test_object_not_found_raises_error` | 抛出 `ObjectNotFoundError` |
| `test_field_term_set_preserved` | 含 `term_set` 的字段解析正确 |
| `test_physical_mappings` | `physical_mappings` 正确解析 DB 列名 / API 路径 |

**计划层**

| 测试 | 验证点 |
|------|-------|
| `test_build_object_view_from_crm` | `ObjectViewPayload` 含正确 sources/objects/relations，含 name/description |
| `test_relations_populated` | relations 含 join_keys 和 description |
| `test_valid_direct_plan` | `PlanValidator` 返回 `valid=True` |
| `test_invalid_step_source_ref` | `valid=False`，errors 含 sourceId 信息 |
| `test_sqlite_missing_csv_table_name` | `valid=False` |
| `test_sql_step_to_exec_task` | `SqlExecTask` 字段映射正确 |
| `test_api_step_to_exec_task` | `ApiExecTask` 字段映射正确 |

**执行层**

| 测试 | 验证点 |
|------|-------|
| `test_api_execute_success` | Mock httpx，CSV 正确写入 |
| `test_api_execute_timeout` | 抛出 `ApiExecutionError` |
| `test_sql_execute_select` | SQLite 替代真实 DB，返回正确 CSV |
| `test_sql_bind_from_step` | 从前序 CSV 读取绑定值，填充占位符正确 |
| `test_direct_aggregator` | 读 CSV 返回正确 records |
| `test_sqlite_aggregator_join` | 多 CSV join 返回正确结果 |

### 7.3 服务层测试

| 测试 | 验证点 |
|------|-------|
| `test_tools_list_returns_unified_and_actions` | 返回 `unified_data_query` + action tools |
| `test_tools_list_missing_header` | 缺少 `X-Tenant-Id` → 400 |
| `test_tools_call_action_success` | Mock ActionExecutor → 返回 records |
| `test_tools_call_term_resolution_error` | 返回工具错误，含可选值列表 |
| `test_rest_query_success` | Mock `View.query` → 返回 `data.records` |

### 7.4 CRM 端到端测试场景

| 场景 | 验证点 |
|------|-------|
| 自然语言查询：「查询邹海天的商机」 | 生成含 owner 过滤的 SQL，records 非空 |
| 跨数据源：「邹海天签了合同的商机」 | API step + SQL step，SQLITE_MEM 聚合，含 contract_id |
| 不可回答：「按合同金额统计」 | `canAnswer=false`，返回 clarification |
| MCP 操作类工具：`query_bo_by_owner` | `tools/call` 直接返回 records，不走 LLM |
| 术语值测试：传"已签约"→"SIGNED" | `TermResolver` 正确映射，API 收到标准 code |

### 7.5 覆盖目标

| 层 | 目标 |
|----|------|
| SDK 核心层（本体、计划、执行、聚合） | ≥ 80% 行覆盖 |
| 服务层（api、tools） | ≥ 70% 行覆盖 |
| CRM 端到端 | 5 个核心场景全部通过 |
