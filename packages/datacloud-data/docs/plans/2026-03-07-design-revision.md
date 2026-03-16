# datacloud-data-service & datacloud-data-sdk 设计修订

> **日期**：2026-03-07
> **状态**：已确认
> **基于**：`2026-03-06-data-service-sdk-design.md` + `数据服务详细设计2.0.md`
> **修订范围**：脚本动作执行、本体 JSON 标准格式、原设计问题修复、开源质量要求

---

## 目录

1. [修订总览](#1-修订总览)
2. [脚本动作执行设计](#2-脚本动作执行设计)
3. [本体 JSON 标准格式](#3-本体-json-标准格式)
4. [原设计问题修复](#4-原设计问题修复)
5. [开源质量要求](#5-开源质量要求)
6. [修订后完整模型汇总](#6-修订后完整模型汇总)
7. [修订后目录结构](#7-修订后目录结构)

---

## 1 修订总览

| 编号 | 修订项 | 类型 | 影响范围 |
|------|--------|------|----------|
| R1 | 动作支持 Python 脚本执行 | 新增功能 | OntologyAction 模型、执行层、服务层 |
| R2 | 统一本体 JSON 标准格式 | 格式变更 | objects_registry.json、OntologyLoader |
| R3 | 补全 View 实体实现 | 补漏 | view.py、OntologyLoader、实现计划 |
| R4 | 配置注入统一到 OntologyLoader | 设计优化 | Object、View、OntologyLoader |
| R5 | camelCase ↔ snake_case 转换 | 补漏 | QueryPlanGenerator |
| R6 | 执行层模型位置统一 | 设计优化 | executor/models、sql_executor/models |
| R7 | BaseAggregator 签名统一 | 设计优化 | PlanAggregation、聚合器 |
| R8 | CSV 清理策略 | 补漏 | csv_storage、Executor |
| R9 | 目录结构迁移 | 工程调整 | src/ 目录 |

---

## 2 脚本动作执行设计

### 2.1 需求

动作（Action）除调用 HTTP API 外，还需支持执行预定义的 Python 脚本。脚本代码与动作绑定，以内联字符串形式存储在本体定义中。

### 2.2 设计决策

| 决策点 | 选择 | 说明 |
|--------|------|------|
| 脚本存放方式 | 内联字符串 | `OntologyAction.script` 字段 |
| 执行约定 | 约定函数签名 | `def execute(params: dict) -> dict` |
| 与 API 的关系 | script 优先 | 有 script 走脚本，否则走 function_refs |
| 脚本能力范围 | 可访问 SDK 上下文 | InvocationContext、httpx、OntologyLoader |

### 2.3 OntologyAction 模型变更

```python
@dataclass
class OntologyAction:
    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]       # API 绑定（可为空）
    script: str | None = None      # Python 脚本代码（内联字符串）
```

### 2.4 ScriptExecutor

新增 `executor/script_executor.py`：

```python
class ScriptExecutor:
    """执行与动作绑定的 Python 脚本。

    脚本约定：必须定义 def execute(params: dict) -> dict
    注入环境：context（RequestContext）、loader（OntologyLoader）、httpx 模块
    """

    def __init__(
        self,
        context_provider: Callable[[], RequestContext],
        ontology_loader: OntologyLoader,
    ) -> None:
        self._context_provider = context_provider
        self._ontology_loader = ontology_loader

    async def execute(
        self,
        script: str,
        params: dict,
        timeout: float = 30.0,
    ) -> dict:
        ...
```

**注入到脚本执行环境的对象**：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `context` | `RequestContext` | 当前请求上下文（tenant_id、token 等） |
| `loader` | `OntologyLoader` | 可查询其他对象/动作 |
| `httpx` | module | HTTP 客户端 |

**脚本示例**：

```python
def execute(params):
    import httpx
    resp = httpx.post(
        "http://crm-api/bo/update",
        json={"bo_id": params["bo_id"], "status": "CLOSED"},
        headers={"Authorization": f"Bearer {context.token}"}
    )
    return {"success": resp.status_code == 200}
```

### 2.5 动作执行分发逻辑

```
Action.execute(params)
  → 有 script 且非空? → ScriptExecutor.execute(script, params)
  → 否则有 function_refs? → ApiExecutor.execute(...)
  → 都没有? → raise ActionNotConfiguredError
```

### 2.6 新增异常

```
ExecutionError
├── ApiExecutionError           （已有）
├── SqlExecutionError           （已有）
├── ScriptExecutionError        （新增）
│   属性: action_code, cause, line_no
└── ActionNotConfiguredError    （新增）
    属性: action_code
```

### 2.7 新增执行任务模型

```python
@dataclass
class ScriptExecTask:
    action_code: str
    script: str
    params: dict
    output_ref: str = ""
```

---

## 3 本体 JSON 标准格式

### 3.1 设计原则

定义一套干净的标准格式，`OntologyLoader` 直接解析，不需要适配层。`objects_registry.json` 按此格式编写或迁移。

### 3.2 顶层结构

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "OBJECT",
  "metadata": {
    "name": "CRM销售场景本体共享库",
    "description": "...",
    "author": "admin",
    "created_time": "2026-03-03T00:00:00Z",
    "tenant_id": "TENANT_001",
    "domain_ref": "sales"
  },
  "functions": [...],
  "objects": [...],
  "relations": [...]
}
```

### 3.3 对象定义

```json
{
  "object_code": "sales_business_opportunity",
  "object_name": "商机对象",
  "description": "CRM系统中的商机，包含阶段、金额等信息",
  "source_type": "DB",
  "datasource_alias": "crm_db",
  "table_name": "sales_business_opportunity",
  "tags": ["商机", "CRM"],
  "fields": [
    {
      "field_code": "bo_id",
      "field_name": "商机ID",
      "field_type": "STRING",
      "description": "商机唯一标识",
      "aliases": ["商机编号"],
      "required": true,
      "is_primary_key": true,
      "source_column": "bo_id"
    },
    {
      "field_code": "stage_code",
      "field_name": "商机阶段",
      "field_type": "STRING",
      "aliases": ["阶段"],
      "term_set": "bo_stage"
    }
  ],
  "actions": [...]
}
```

**source_type 取值**：

| source_type | 说明 | 原 object_type |
|-------------|------|---------------|
| `DB` | 数据库表/视图 | ANALYTICS_DB |
| `API` | HTTP API 数据源 | API |
| `KNOWLEDGE_BASE` | 知识库（Phase 2） | KNOWLEDGE_BASE |

### 3.4 动作定义（含 script）

```json
{
  "action_code": "query_bo_by_owner",
  "action_name": "按负责人查商机",
  "description": "通过负责人ID查询商机列表",
  "script": null,
  "function_refs": ["fn_crm_bo_query"],
  "visible": true,
  "tags": ["查询"],
  "params": [
    {
      "param_code": "owner_id",
      "param_name": "负责人ID",
      "param_type": "STRING",
      "direction": "IN",
      "required": true,
      "mapping_path": "$.requestBody.ownerId",
      "term_set": null
    },
    {
      "param_code": "bo_list",
      "param_name": "商机列表",
      "param_type": "ARRAY",
      "direction": "OUT",
      "mapping_path": "$.response.data"
    }
  ]
}
```

**脚本动作示例**：

```json
{
  "action_code": "calculate_bo_score",
  "action_name": "计算商机评分",
  "description": "根据商机阶段和金额计算综合评分",
  "script": "def execute(params):\n    stage = params['stage_code']\n    amount = params.get('amount', 0)\n    score_map = {'INITIAL': 10, 'NEGOTIATION': 50, 'SIGNED': 100}\n    base = score_map.get(stage, 0)\n    return {'score': base + min(amount / 10000, 50)}",
  "function_refs": [],
  "params": [
    {"param_code": "stage_code", "param_name": "商机阶段", "param_type": "STRING", "direction": "IN", "required": true},
    {"param_code": "amount", "param_name": "金额", "param_type": "NUMBER", "direction": "IN"},
    {"param_code": "score", "param_name": "评分", "param_type": "NUMBER", "direction": "OUT"}
  ]
}
```

### 3.5 关系定义

```json
{
  "relation_code": "bo_to_contract",
  "relation_name": "商机关联合同",
  "source_class": "sales_business_opportunity",
  "target_class": "sales_contract",
  "relation_type": "ONE_TO_MANY",
  "join_keys": [
    {"from_field": "bo_id", "to_field": "bo_id"}
  ],
  "description": "一个商机可签署多份合同"
}
```

### 3.6 与现有 JSON 的字段映射

| 现有字段 | 标准格式 | 变更原因 |
|---------|---------|---------|
| `properties[]` | `fields[]` | 与 OntologyField 模型一致 |
| `property_code` | `field_code` | 同上 |
| `property_name` | `field_name` | 同上 |
| `property_type` | `field_type` | 同上 |
| `object_type` | `source_type` | 简化语义，DB/API/KNOWLEDGE_BASE |
| 内嵌 `source_config{}` | `datasource_alias` + `table_name` | 数据源配置外置到 settings.yaml |
| `source_object_ref` | `source_class` | 与 OntologyRelation 模型一致 |
| `target_object_ref` | `target_class` | 同上 |
| `source_property_ref`/`target_property_ref` | `join_keys[]` | 结构化，支持复合键 |
| `param_bindings`（字段上） | 去掉 | 参数在 action.params 中定义 |
| `termMeta`（参数上） | `term_set`（字符串） | 简化，term_set 指向术语集 ID |

---

## 4 原设计问题修复

### 4.1 R3: 补全 View 实体

- `view.py` 在 P1.1 阶段实现
- `OntologyLoader.get_view(view_id)` 从 scene 文件加载场景定义（包含 object_ids），内部调 `get_object()` 组装
- `View.query()` 委托给 ObjectViewBuilder → 查询链路，与 `Object.query()` 共享计划/执行/聚合管线

### 4.2 R4: 配置注入统一到 OntologyLoader

去掉 `Object.set_*()` / `Object.configure()`。统一在 `OntologyLoader` 上配置：

```python
loader = OntologyLoader()
loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
loader.configure(
    plan_generator=LangGraphPlanGenerator(...),
    datasource_configs={"crm_db": DataSourceConfig(...)},
    csv_base_dir="/tmp/datacloud_csv",
)

obj = loader.get_object("sales_bo")     # 继承 loader 配置
view = loader.get_view("scene_01")      # 继承 loader 配置
```

### 4.3 R5: camelCase ↔ snake_case 转换

LLM 返回 camelCase JSON，Python 模型用 snake_case。在 `QueryPlanGenerator` 中增加工具函数 `camel_to_snake_keys(d: dict) -> dict` 做递归转换。

### 4.4 R6: 执行层模型位置统一

| 文件 | 定义的模型 |
|------|-----------|
| `executor/models.py` | `ApiExecTask`、`ScriptExecTask` |
| `sql_executor/models.py` | `DataSourceConfig`、`SqlExecTask`、`SqlExecResult` |

不重复定义。

### 4.5 R7: BaseAggregator 签名统一

将 `csv_table_names` 放入 `PlanAggregation`：

```python
@dataclass
class PlanAggregation:
    strategy: str
    final_step_id: str | None = None
    sqlite_sql: str | None = None
    columns: list[dict] = field(default_factory=list)
    csv_table_names: dict[str, str] = field(default_factory=dict)
```

`BaseAggregator.aggregate(agg, step_results)` 签名统一，不需要额外参数。

### 4.6 R8: CSV 清理策略

```python
async def query(self, question: str) -> dict:
    request_id = str(uuid.uuid4())
    try:
        # ... 计划 → 执行 → 聚合 ...
        return {"records": records, "meta": meta}
    finally:
        csv_manager.cleanup(request_id)
```

### 4.7 R9: 目录结构迁移

删除 `src/datacloud_data_service/` 下的 SDK 子目录（ontology、plan、executor、aggregator、events、csv_storage、sql_executor），新建 `src/datacloud_data_sdk/` 及其子目录。`datacloud_data_service` 只保留 `api/` 和 `tools/`。

---

## 5 开源质量要求

### 5.1 包设计

- **公开 API 面**：`datacloud_data_sdk/__init__.py` 仅暴露 `OntologyLoader`、`View`、`Object`、`Action`、`Relation`、`InvocationContext`、`DatacloudError` 及子类
- **可选依赖**：核心本体层零外部依赖；LangGraph / SQL 驱动 / httpx 为可选 extras
- **抽象接口**：`BasePlanGenerator(ABC)`、`BaseAggregator(ABC)`、`BaseSourceConnector(ABC)` 允许替换实现

### 5.2 代码规范

- 全量类型注解（`mypy --strict` 通过）
- 异步优先（所有 I/O 为 `async/await`）
- docstring（Google 风格）覆盖所有公开类和方法
- 无 `# type: ignore` 压制（除第三方类型桩缺失）

### 5.3 文档

- `README.md`：快速开始、安装、基本用法
- `CONTRIBUTING.md`：开发环境搭建、PR 流程
- `docs/`：API 参考（可用 mkdocs 生成）
- 每个公开类/函数有 docstring 示例

### 5.4 测试

- pytest + pytest-asyncio + pytest-mock
- 覆盖率目标：SDK ≥ 80%，服务层 ≥ 70%
- 集成测试与 CRM Demo 端到端测试

### 5.5 CI/CD

- `pyproject.toml` 完整配置 ruff（lint）、mypy（类型检查）、pytest
- pre-commit hooks：ruff format + ruff check + mypy

---

## 6 修订后完整模型汇总

### 6.1 本体层模型（ontology/models.py）

```python
@dataclass
class FieldPhysicalMapping:
    source_type: str          # DB / API
    source_ref: str           # DB 列名 或 API 参数路径
    datasource_alias: str

@dataclass
class OntologyField:
    field_code: str
    field_name: str
    field_type: str           # STRING / NUMBER / DATE / BOOLEAN / INTEGER / ARRAY / OBJECT
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    is_primary_key: bool = False
    source_column: str | None = None
    term_set: str | None = None
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)

@dataclass
class OntologyActionParam:
    param_code: str
    param_name: str
    direction: str            # IN / OUT / INOUT
    param_type: str
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""
    term_set: str | None = None

@dataclass
class OntologyAction:
    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]
    script: str | None = None       # ← 新增

@dataclass
class OntologyRelation:
    relation_code: str
    relation_name: str = ""
    source_class: str = ""
    target_class: str = ""
    relation_type: str = ""         # ONE_TO_MANY / MANY_TO_ONE / ONE_TO_ONE / MANY_TO_MANY
    join_keys: list[dict] = field(default_factory=list)
    description: str = ""

@dataclass
class OntologyClass:
    object_code: str
    object_name: str
    description: str
    source_type: str              # DB / API / KNOWLEDGE_BASE
    datasource_alias: str | None = None
    table_name: str | None = None
    tags: list[str] = field(default_factory=list)
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)
```

### 6.2 执行层模型

```python
# executor/models.py
@dataclass
class ApiExecTask:
    function_code: str
    params: dict
    output_ref: str
    csv_table_name: str | None = None

@dataclass
class ScriptExecTask:
    action_code: str
    script: str
    params: dict
    output_ref: str = ""

# sql_executor/models.py
@dataclass
class DataSourceConfig:
    alias: str
    db_type: str              # MYSQL / POSTGRESQL / CLICKHOUSE / SQLITE / DORIS
    jdbc_url: str
    user: str = ""
    password: str = ""
    pool_max_size: int = 10
    pool_timeout: int = 3000

@dataclass
class SqlExecTask:
    datasource_alias: str
    sql_template: str
    bind_from_step: str | None = None
    bind_key: str | None = None
    output_ref: str = ""
    csv_table_name: str | None = None

@dataclass
class SqlExecResult:
    csv_path: str
    row_count: int
```

### 6.3 计划层模型（含 csv_table_names 统一）

```python
@dataclass
class PlanAggregation:
    strategy: str                  # DIRECT / SQLITE_MEM
    final_step_id: str | None = None
    sqlite_sql: str | None = None
    columns: list[dict] = field(default_factory=list)
    csv_table_names: dict[str, str] = field(default_factory=dict)  # ← 移入此处
```

### 6.4 异常层次（完整）

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
│   ├── ScriptExecutionError(action_code, cause, line_no)     ← 新增
│   ├── ActionNotConfiguredError(action_code)                  ← 新增
│   └── DataSourceUnavailableError(alias)
└── AggregationError(strategy, sql, cause)
```

---

## 7 修订后目录结构

```
datacloud-data-service/
├── resources/
│   └── ontology/
│       └── crm_demo/
│           ├── objects_registry.json      # 标准格式
│           └── scene_01_data_analysis.json
├── src/
│   ├── datacloud_data_sdk/                # SDK 子包
│   │   ├── __init__.py                    # 公开 API 面
│   │   ├── context.py                     # InvocationContext
│   │   ├── view.py                        # View 实体         ← 补全
│   │   ├── object.py                      # Object 实体
│   │   ├── action.py                      # Action 实体
│   │   ├── relation.py                    # Relation 模型
│   │   ├── exceptions.py                  # 异常层次
│   │   ├── ontology/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                  # 含 script 字段
│   │   │   ├── loader.py                  # OntologyLoader + configure()
│   │   │   └── term_loader.py
│   │   ├── plan/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                  # 含 csv_table_names 统一
│   │   │   ├── object_view_builder.py
│   │   │   ├── query_plan_generator.py    # 含 camel_to_snake 转换
│   │   │   ├── plan_validator.py
│   │   │   ├── data_permission_rewriter.py
│   │   │   └── execution_object_converter.py
│   │   ├── executor/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                  # ApiExecTask + ScriptExecTask
│   │   │   ├── executor.py
│   │   │   ├── api_executor.py
│   │   │   ├── script_executor.py         # ← 新增
│   │   │   └── sql_executor_adapter.py
│   │   ├── sql_executor/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                  # DataSourceConfig + SqlExecTask
│   │   │   ├── base_connector.py
│   │   │   ├── connector_registry.py
│   │   │   ├── connectors/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── sqlite_connector.py
│   │   │   │   ├── mysql_connector.py
│   │   │   │   ├── postgresql_connector.py
│   │   │   │   └── clickhouse_connector.py
│   │   │   ├── data_source_manager.py
│   │   │   ├── sql_executor.py
│   │   │   ├── result_converter.py
│   │   │   └── jdbc_parser.py
│   │   ├── aggregator/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── direct_aggregator.py
│   │   │   └── sqlite_aggregator.py
│   │   ├── events/
│   │   │   ├── __init__.py
│   │   │   ├── bus.py
│   │   │   ├── events.py
│   │   │   ├── handlers.py
│   │   │   └── tracing.py
│   │   └── csv_storage/
│   │       ├── __init__.py
│   │       └── manager.py                 # 含 cleanup()
│   │
│   └── datacloud_data_service/            # 服务子包（薄壳）
│       ├── __init__.py
│       ├── config.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py
│       │   ├── query.py
│       │   ├── mcp_handler.py
│       │   └── skills.py
│       └── tools/
│           ├── __init__.py
│           ├── registry.py
│           ├── unified_query.py
│           ├── action_tool_generator.py
│           ├── action_executor.py
│           ├── param_mapper.py
│           └── term_resolver.py
│
├── tests/
│   ├── datacloud_data_sdk/
│   │   ├── test_exceptions.py
│   │   ├── test_context.py
│   │   ├── test_ontology_models.py
│   │   ├── test_ontology_loader.py
│   │   ├── test_term_loader.py
│   │   ├── test_sdk_entities.py
│   │   ├── test_script_executor.py        # ← 新增
│   │   ├── test_object_view_builder.py
│   │   ├── test_plan_validator.py
│   │   ├── test_execution_object_converter.py
│   │   ├── test_connector_registry.py
│   │   ├── test_sql_executor.py
│   │   ├── test_api_executor.py
│   │   ├── test_aggregator.py
│   │   ├── test_event_bus.py
│   │   ├── test_tracing.py
│   │   └── integration/
│   │       ├── test_ontology_loader_integration.py
│   │       └── test_query_pipeline_integration.py
│   ├── datacloud_data_service/
│   │   ├── test_health.py
│   │   ├── test_mcp_tools_list.py
│   │   ├── test_mcp_tools_call.py
│   │   └── test_rest_query.py
│   └── e2e/
│       └── test_crm_scenarios.py
├── pyproject.toml
├── README.md
└── CONTRIBUTING.md
```
