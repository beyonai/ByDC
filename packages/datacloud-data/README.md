# datacloud-data

## 简介

datacloud-data 是dataCloud平台的数据虚拟化模块，负责把本体语义语言转化为物理检索或物理操作的数据库语言，并返回执行结果。



## 定位

面向本体语言提供跨数据源、跨数据服务、跨数据结构的数据虚拟化服务。

- **跨数据源**：允许把两个不同数据源的数据表虚拟成一个本体对象或本体数据。

- **跨数据服务**：允许把两个不同数据服务（一个DB数据库表，一个是API）虚拟成一个本体对象或本体视图。
- **跨数据结构**：允许把两个不同数据结构（一个DB数据库表，一个是文档）虚拟成一个本体对象或本体数据。



## 架构设计

### 项目结构

```
packages/datacloud-data/
├── config/                         # 数据源配置示例
├── docs/                           # 设计文档与实施计划
├── examples/                       # 可运行 SDK 示例
├── resources/                      # 包内 OWL 对象与视图资源
├── src/
│   ├── datacloud_data_sdk/
│   │   ├── ontology/               # 本体加载与解析（OntologyLoader）
│   │   ├── plan/                   # 查询计划生成与校验（LangGraphPlanGenerator）
│   │   ├── executor/               # 查询与动作执行器
│   │   ├── sql_executor/           # SQL 执行与连接器
│   │   ├── aggregator/             # 结果聚合
│   │   ├── virtual_action/         # 虚拟动作生成与校验
│   │   ├── oql/                    # OQL 适配与路由
│   │   ├── agents/                 # LLM Agent
│   │   ├── csv_storage/            # CSV 大文件存储
│   │   ├── file_storage/           # 本地结果文件存储
│   │   ├── events/                 # 事件总线与追踪
│   │   ├── graphql/                # GraphQL 支持
│   │   └── utils/                  # 通用工具函数
│   └── datacloud_data_service/
│       ├── api/                    # REST、MCP 与 GraphQL 路由
│       ├── resource/               # 服务内置 Agent、对象与视图资源
│       └── tools/                  # MCP 工具与技能包生成
└── tests/                          # 单元测试与集成测试
```

### 核心模块说明

#### `OntologyLoader` — 本体加载入口

```python
loader = OntologyLoader()
loader.load_from_owl_resource_directory(path)   # 从 OWL 资源目录加载
loader.load_from_content(registry_dict)          # 从字典加载（测试/内嵌场景）
loader.configure(plan_generator=..., ...)        # 注入 LLM 规划器、数据源配置等
```

加载后可通过 `loader.get_object(code)` / `loader.get_view(view_id)` 获取运行时对象。

#### 查询执行链路

```
用户问题（自然语言）
  → LangGraphPlanGenerator（LLM 生成查询计划）
  → 计划校验（跨源 JOIN 检测、字段合法性）
  → Executor 分发：
      ├── SQL 步骤 → SqlExecutor（SQLAlchemy / ClickHouse）
      ├── API 步骤 → HttpExecutor（参数映射 + 响应抽取）
      └── 虚拟动作 → VirtualActionExecutor
  → Aggregator（同源下沉 / 跨源联邦合并）
  → 结果格式化（术语值转换 + CSV 溢出导出）
```

#### SDK 常用入口

| 方法 | 说明 |
|------|------|
| `loader.get_object(object_code)` | 获取单个对象 |
| `loader.get_view(view_id)` | 获取预定义视图 |
| `await obj.query(question)` | 按对象执行自然语言查询 |
| `await view.query(question)` | 按视图执行自然语言查询 |
| `obj.list_action_codes()` | 列出对象可执行动作 |
| `obj.get_action_schema(action_code)` | 查看动作参数 Schema |
| `await obj.invoke_action(action_code, params)` | 直接执行对象动作 |
| `await view.invoke_object_action(obj_code, action_code, params)` | 通过视图调用对象动作 |

### REST API

```bash
# 自然语言查询
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: tenant-001" -H "X-User-Id: user-001" \
  -d '{"question": "查询项目列表", "object_ids": ["by_project"]}'

# 列出 MCP Tools
curl -X POST http://localhost:8080/api/v1/mcp \
  -H "Content-Type: application/json" \
  -H "X-Object-Ids: by_project" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'

# 获取技能包
curl "http://localhost:8080/api/v1/skills/package?object_ids=by_project" \
  -H "X-Tenant-Id: tenant-001"
```

---

## 插件与扩展

### 自定义 PlanGenerator

实现 `PlanGenerator` 协议即可替换默认的 LLM 规划器：

```python
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator

loader.configure(plan_generator=MockPlanGenerator(fixed_plan=MY_PLAN))
```

生产环境使用 `LangGraphPlanGenerator`，测试环境使用 `MockPlanGenerator`。

### 自定义数据源连接器

在本体对象的 `source_config` 中配置 `db_type`，SDK 会自动选择对应连接器：

| db_type | 连接器 | 依赖 Extra |
|---------|--------|-----------|
| `SQLITE` | SQLite（内置） | — |
| `POSTGRESQL` / `MYSQL` | SQLAlchemy | `sql` |
| `CLICKHOUSE` | ClickHouse 异步驱动 | `clickhouse` |
| `HTTP_API` | HttpExecutor | — |

### 虚拟动作（Virtual Action）

`virtual_action/` 模块根据本体对象的字段定义自动生成 `query_*` / `compute_*` 工具描述和参数 Schema，供 `datacloud-analysis` 的 LLM 直接调用，无需手写工具定义。

---



---

## 开发指南

```bash
# 格式化 + Lint
uv run ruff format src/by_datacloud packages
uv run ruff check src/by_datacloud packages --fix

# 类型检查
uv run mypy src/by_datacloud packages
```

关键约定：

- Python >= 3.12，完整类型注解，MyPy strict mode
- 改动应尽量收敛在当前包内，避免影响跨包 API 契约
- 实现变更需同步补充或更新测试

---

## 测试

```bash
# 全部测试
uv run pytest packages/datacloud-data/tests

# 仅单元测试
uv run pytest packages/datacloud-data/tests/unit -v

# 带覆盖率
uv run pytest packages/datacloud-data/tests --cov=datacloud_data_sdk --cov-report=term-missing
```

集成测试需要配置真实数据源连接，默认跳过，通过 `-m db_integration` 标记单独运行。
