# OQL 翻译规则方案设计

> 文档版本：v1.1  
> 适用模块：`datacloud-data`（执行引擎）  
> 依赖文档：`本体推理引擎重构方案.md § 2.2`（OQL 协议定义）  
> 设计目标：**基于现有代码实现，将 OQL 100% 转化为可执行的 SQL / API 调用**



---

## 1. 架构设计

### 1.1 改前架构：LLM 生成 SQL 模板

现有 `datacloud-data` 的唯一查询路径是 **自然语言 → LLM 生成 SQL 模板 → 执行**。整条链路如下：

```
外部调用方（datacloud-analysis / MCP 客户端）
         │ 自然语言问题（string）
         ▼
  UnifiedQuery.execute()                      datacloud_data_service/tools/unified_query.py
         │
         ├─ view_id 指定  → View.query()      datacloud_data_sdk/view.py
         └─ object_id 指定 → Object.query()   datacloud_data_sdk/object.py
                  │
                  ▼
         ObjectViewBuilder.build()            plan/object_view_builder.py
         │  构建 ObjectViewPayload（本体元数据快照）
         ▼
  ┌─────────────────────────────────────┐
  │  LangGraphPlanGenerator.generate()  │   plan/query_plan_generator.py
  │  · 将 ObjectViewPayload + 问题       │   ← 依赖 LLM（OpenAI/兼容接口）
  │    送给 LLM                          │
  │  · LLM 直接生成 SQL 模板字符串        │
  │  · 返回 QueryExecutionPlan           │
  │    （含 PlanStep.sql_template）       │
  └─────────────────────────────────────┘
         │ QueryExecutionPlan
         ▼
  ExecutionObjectConverter.convert()          plan/execution_object_converter.py
  │  PlanStep(type=SQL)  → SqlExecTask
  │  PlanStep(type=API)  → ApiExecTask
  │  PlanStep(type=KB)   → KbExecTask
  │  （术语解析：sql_term_resolver，resolve_sql_literals）
         │
         ▼
  Executor.run()                              executor/executor.py
  │  SqlExecTask  → SqlExecutor.execute()     sql_executor/sql_executor.py
  │  ApiExecTask  → ApiExecutor.execute()     executor/api_executor.py
  │  KbExecTask   → KbExecutor.execute()      executor/kb_executor.py
         │
         ▼
  Aggregator（DIRECT / SQLITE_MEM）           aggregator/
         │
         ▼
  build_query_response()                      result_formatter.py
```

**现有架构的关键特点：**

| 特点 | 说明 |
|------|------|
| SQL 由 LLM 直接生成 | `PlanStep.sql_template` 是 LLM 输出的原始 SQL 字符串 |
| 本体元数据通过 Payload 传给 LLM | `ObjectViewPayload` 包含表名、字段名、关系等，作为 Prompt 上下文 |
| 术语解析在 SQL 字符串上做正则替换 | `sql_term_resolver.resolve_sql_literals()` 扫描 SQL 字符串 |
| 无结构化 OQL 中间层 | 自然语言直接变成 SQL，没有中间结构化的查询描述 |
| 方言由 LLM 负责 | LLM 生成的 SQL 语法取决于 Prompt 中的方言提示 |

**现有架构存在的问题：**
- LLM 生成的 SQL 容易出现幻觉字段名、错误表连接，难以调试
- 方言适配依赖 Prompt 质量，不稳定
- 无法对查询参数做结构化校验（字段是否存在、操作符是否合法）
- 每次查询都需要 LLM 调用，延迟高

---

### 1.2 目标架构：OQL 结构化翻译（新增并行链路）

新增 **OQL 翻译链路**，作为现有 LLM 生成链路的**并行替代**，两条链路共享同一个 `Executor`。

**改动原则：只新增，不修改任何现有文件。**

> **设计决策**：OQL 翻译层（`oql/adapter.py`）**自建**了一套轻量的 SQL 构建函数（原子翻译层），而非复用 `DynamicQueryExecutor`。原因如下：
> - `DynamicQueryExecutor` 的 WHERE / GROUP BY / JOIN 格式与 OQL 结构有差异，适配成本高于重建
> - 原子翻译层函数需要清晰可测，与 OQL 字段语义一一对应
> - 新链路只生成 `SqlExecTask`（datasource_alias + sql_template），由已有的 `SqlExecutor → connector.execute()` 负责执行，两端完全解耦
>
> `DynamicQueryExecutor` 继续服务于旧 LLM 链路，不受影响。

#### 1.2.1 整体执行路径

```
外部调用方（datacloud-analysis）
         │
         ├─── [现有路径，不动] 自然语言 ──────────────────────────────────┐
         │                                                               │
         │    UnifiedQuery / View.query() / Object.query()               │
         │    → ObjectViewBuilder → LangGraphPlanGenerator（LLM 生成 SQL）│
         │    → ExecutionObjectConverter → Executor.run()                │
         │                                                               │
         └─── [新增路径] OQL JSON（结构化） ──────────────────────────────┤
                          │                                              │
                          ▼                                              │
              ┌─────────────────────────────────────────┐               │
              │  OqlRouter  （新增）                      │               │
              │  oql/router.py                           │               │
              │                                         │               │
              │  判断执行模式（按顺序检测，命中即路由）：   │               │
              │  1. 顶层是数组 → Pipeline 模式            │               │
              │  2. DB 主对象的 include_links 存在 &&     │               │
              │     目标对象跨源或为 API → 跨源模式        │               │
              │     (API 主对象 + include_links 在前置     │               │
              │      约束检查中直接失败，不进入此分支)       │               │
              │  3. 其余 → 单源模式                       │               │
              └──────┬──────────┬──────────┬────────────┘               │
                     │          │           │                            │
              ┌──────▼──┐  ┌───▼──────┐  ┌▼──────────────┐            │
              │ 策略 A  │  │ 策略 B   │  │   策略 C       │            │
              │ 单源执行 │  │ 跨源执行  │  │ Pipeline 执行  │            │
              └──────┬──┘  └───┬──────┘  └┬──────────────┘            │
                     │          │           │ 每步降为策略A/B             │
                     │          │           │                            │
                     │    ┌─────▼───────────▼──────────────────┐        │
                     │    │  结果在内存中按关联键合并              │        │
                     │    │  oql/memory_merger.py  （新增）      │        │
                     │    └──────────────┬─────────────────────┘        │
                     │                   │                               │
                     └─────────┬─────────┘                              │
                               ▼                                         │
                     Executor.run()  ← 不动，共用 ───────────────────────┘
                               │
                               ▼
                     Aggregator / result_formatter  ← 不动，共用
```

---

#### 1.2.2 策略 A：单源执行

适用于：主对象与所有 `include_links` 目标对象均在**同一数据源**，或主对象为 API 类型（无关联）。

```
OQL JSON（单步）
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  OqlAdapter  （新增）                                 │
│  oql/adapter.py                                      │
│                                                      │
│  DB 对象：                                            │
│  · preprocess_where_terms()   术语预处理              │
│  · build_field_map()          字段解析（三级回退）     │
│  · [有 metrics] build_aggregate_sql()  聚合路径       │
│  · [无 metrics] _build_list_sql()      列表路径       │
│    ├─ translate_conditions()  WHERE 翻译              │
│    └─ resolve_include_links() 同源 JOIN 翻译          │
│  · normalize_sql_params()     方言占位符适配           │
│  → SqlExecTask(datasource_alias, sql_template)       │
│                                                      │
│  API 对象：                                           │
│  · _select_query_action()     选 action              │
│  · where eq/in → params 映射                         │
│  · order_by → sort 参数注入                           │
│  → ApiExecTask(object_code, action_code, params)     │
└────────────────────┬─────────────────────────────────┘
                     │
          ┌──────────▼──────────────────────────────┐
          │          Executor.run()（已有，不动）      │
          │  SqlExecTask → SqlExecutor               │
          │              → connector.execute()       │
          │  ApiExecTask → ApiExecutor               │
          └─────────────────────────────────────────┘
```

---

#### 1.2.3 策略 B：跨源执行

适用于：`include_links` 目标对象与主对象**数据源不同**（不同 `datasource_alias`），或目标对象为 **API 类型**。无法下推 SQL JOIN，改为两阶段查询 + 内存合并。

```
OQL JSON（含跨源 include_links）
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  CrossSourceExecutor  （新增）                        │
│  oql/cross_source_executor.py                        │
│                                                      │
│  Phase 1：查主对象                                    │
│  · classify_include_links() 分离同源/跨源 links       │
│  · 同源 links 保留 → 策略 A 执行（可下推 SQL JOIN）    │
│  · 获得主表 main_records                              │
│                                                      │
│  Phase 2：逐跳查关联对象 + 内存合并（循环，每跳一次）   │
│  · 提取主表中关联键值列表（去重，过滤 None）             │
│  · 键值超 1000 条 → 自动分批，合并结果                 │
│  · 若目标 source_type == DB：                         │
│    构造 { where: [关联键 in 键值列表] } → 策略 A 执行  │
│  · 若目标 source_type == API：                        │
│    将键值列表注入 API IN 参数     → 策略 A 执行        │
│  · MemoryMerger.left_join() 将子查询结果合并到主表     │
│    列名前缀：{path}__{field}（与策略 A SQL 别名一致）  │
└──────────────────────────────────────────────────────┘
         │
         ▼
返回合并后的 main_records（list[dict]）
```

**跨源判断逻辑**：由 `classify_include_links()` 负责（见 §2.3.1），分别返回同源组和跨源组，路由层判断跨源组非空即进入策略 B。

---

#### 1.2.4 策略 C：Pipeline 执行

适用于：OQL 顶层为**数组**（多步组合），步骤间通过 `$ref` 传递结果。

```
OQL Pipeline（数组）
[
  { "step_id": "s1", "tool": "QueryObjects", "parameters": {...} },
  { "step_id": "s2", "tool": "QueryObjects", "parameters": { "where": [
      { "field": "机型", "op": "in", "value": { "$ref": "s1.result[*].机型" } }
  ]} }
]
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  PipelineExecutor  （新增）                           │
│  oql/pipeline_executor.py                            │
│                                                      │
│  顺序执行每个 step：                                   │
│  1. RefResolver.resolve(step.parameters, context)    │
│     · 扫描 parameters 中所有 "$ref" 值               │
│     · "s1.result[*].机型" →                         │
│       从 context["s1"].records 中提取 "机型" 列       │
│       → 去重列表，替换为实际值                         │
│  2. 将解析后的 parameters 路由至策略 A 或策略 B 执行   │
│  3. 将执行结果写入 context[step_id]                   │
│                                                      │
│  最终返回：最后一步的结果（或全部步骤结果，由调用方决定） │
└──────────────────────────────────────────────────────┘

$ref 表达式语法：
  "{step_id}.result[*].{field}"  → 提取指定 step 结果中某列的所有值（去重列表）
  "{step_id}.result[0].{field}"  → 提取第一行某列的标量值
```

---

#### 1.2.5 三种策略对比

| 维度 | 策略 A：单源执行 | 策略 B：跨源执行 | 策略 C：Pipeline |
|------|:---:|:---:|:---:|
| 触发条件 | 单对象或同源关联 | include_links 跨源/含API | OQL 顶层为数组 |
| JOIN 方式 | SQL LEFT JOIN（下推DB） | 内存 LEFT JOIN（两阶段） | 步骤间 $ref 注入 |
| 网络往返 | 1 次 | N 跳各 1 次 | 步骤数次 |
| 聚合下推 | ✅ 数据库执行 | ❌ 主表聚合可下推，关联不行 | 各步骤独立 |
| API 对象支持 | ✅（主对象为API） | ✅（关联对象为API） | ✅ |
| 新增代码 | `oql/adapter.py` | `oql/cross_source_executor.py` | `oql/pipeline_executor.py` |
| 共用代码 | `SqlExecutor` / `ApiExecutor` | 策略A + `oql/memory_merger.py` | 策略A/B |

---

### 1.3 文件变更清单

#### 1.3.1 新增文件（6 个）

| 文件 | 对应章节 | 职责 | 行数估计 |
|------|---------|------|---------|
| `oql/__init__.py` | — | 包入口，统一导出 `OqlRouter` | ~10 行 |
| `oql/router.py` | §2.5 | 入口路由：Schema 校验 → 策略分派 | ~60 行 |
| `oql/adapter.py` | §2.2 | 策略 A：OQL → `SqlExecTask` / `ApiExecTask` | ~180 行 |
| `oql/cross_source_executor.py` | §2.3 | 策略 B：两阶段跨源执行 + `classify_include_links` | ~100 行 |
| `oql/pipeline_executor.py` | §2.4 | 策略 C：Pipeline 顺序执行 + `RefResolver` | ~80 行 |
| `oql/memory_merger.py` | §2.3.3 | 内存 LEFT JOIN 工具，策略 B 专用 | ~40 行 |

> 原子翻译层（§2.1）的所有函数（`resolve_column`、`translate_conditions`、`build_aggregate_sql` 等）全部实现在 `oql/adapter.py` 中，以 module-level 函数形式导出，供 `OqlAdapter` 和 `CrossSourceExecutor` 调用。

#### 1.3.2 修改文件（1 个）

| 文件 | 修改内容 |
|------|---------|
| `sql_executor/connector_registry.py` | 新增数据库方言注册（如 Spark）时在此追加 `ConnectorRegistry.register(...)` |

> 仅在扩展新数据库类型时才需修改，常规 OQL 翻译功能开发无需改动此文件。

#### 1.3.3 不动的现有文件

| 文件/目录 | 被哪个新文件调用 |
|-----------|----------------|
| `executor/models.py`（`SqlExecTask`、`ApiExecTask`） | `oql/adapter.py` 输出任务对象 |
| `executor/executor.py`（`Executor.run()`） | `oql/router.py` 通过 `executor` 参数传入 |
| `sql_executor/sql_executor.py`（`SqlExecutor`） | `Executor` 内部调用，链路不变 |
| `sql_executor/connector_registry.py` + 各 Connector | `SqlExecutor` 内部调用，链路不变 |
| `executor/api_executor.py`（`ApiExecutor`） | `Executor` 内部调用，链路不变 |
| `ontology/`（`OntologyRegistry`、`OntologyClass` 等） | 所有新文件均依赖，只读 |
| `plan/term_resolver.py`（`TermResolver`） | `oql/adapter.py` 调用术语解析 |
| `plan/`、`view.py`、`object.py` | LLM 旧链路，完整保留，与新 OQL 链路并行 |

---

### 1.4 两条链路对比

| 维度 | 现有链路（LLM 生成 SQL） | 新增链路（OQL 结构化翻译） |
|------|------------------------|------------------------|
| 输入格式 | 自然语言字符串 | OQL JSON（结构化） |
| SQL 生成方式 | LLM 直接输出 SQL 字符串 | 纯规则翻译，确定性 |
| LLM 依赖 | 是（每次查询调用 LLM） | 否（LLM 在上游 datacloud-analysis 完成） |
| 方言适配 | Prompt 引导，不稳定 | 规则代码，100% 可控 |
| 字段校验 | 事后校验（执行报错才发现） | 事前结构化校验，即时报错 |
| 可调试性 | 黑盒（LLM 输出不可预期） | 白盒（每步中间产物可打印） |
| 延迟 | 高（LLM RTT + 生成耗时） | 低（纯计算，毫秒级） |
| 核心 SQL 构建 | LLM 生成字符串，经 `DynamicQueryExecutor` 执行 | `oql/adapter.py` 原子翻译层自建，生成 `SqlExecTask` 交由 `SqlExecutor` 执行 |
| 新增代码量 | — | 6 个新文件合计约 470 行（`adapter.py` ~180 + `router.py` ~60 + `cross_source_executor.py` ~100 + `pipeline_executor.py` ~80 + `memory_merger.py` ~40 + `__init__.py` ~10） |
| 入口 | `View.query()` / `Object.query()` | `OqlRouter.route()` → 策略 A/B/C → `Executor.run()` |

---

### 1.5 整体翻译流水线

```
OQL JSON（来自 datacloud-analysis）
         │
         ▼
  ┌──────────────────────────┐
  │  1. JSON Schema 校验      │  jsonschema.validate(oql, OQL_SCHEMA)
  └──────────┬───────────────┘  失败 → OQL_ERR_SCHEMA_INVALID
             │
             ▼
  ┌──────────────────────────┐
  │  2. 类型判断              │  isinstance(oql, list)？
  └──────────┬───────────────┘
             │ 是 → Pipeline 模式
             │      PipelineExecutor.execute()
             │      （每步递归走下方流水线）
             │
             │ 否 → 单步模式，继续 ↓
             ▼
  ┌──────────────────────────┐
  │  3. 对象解析 + 前置校验   │  resolve_object(object_type)
  └──────────┬───────────────┘  失败 → OQL_ERR_UNKNOWN_OBJECT_TYPE
             │  · API + metrics      → OQL_ERR_UNSUPPORTED_OPERATION
             │  · API + include_links → OQL_ERR_UNSUPPORTED_OPERATION
             │  · Hive + offset > 0  → warning，截断为 0
             ▼
  ┌──────────────────────────┐
  │  4. 路由判断              │  classify_include_links()
  └──────────┬───────────────┘
             │  跨源 include_links 存在 → 策略 B（CrossSourceExecutor）
             │  否则                   → 策略 A（OqlAdapter）
             ▼
  ┌─────────────────────────────────────────────────────┐
  │  5a. 策略 A — 原子翻译层（DB 对象）                   │
  │      ├─ preprocess_where_terms()  术语预处理          │
  │      ├─ build_field_map()         字段解析（三级回退） │
  │      ├─ translate_conditions()    WHERE 翻译          │
  │      ├─ resolve_include_links()   同源 JOIN 翻译      │
  │      ├─ build_aggregate_sql()     聚合翻译（有 metrics）│
  │      ├─ get_quoting() / inline_value() 方言适配      │
  │      └─ → SqlExecTask                               │
  │                                                     │
  │  5b. 策略 A — 原子翻译层（API 对象）                  │
  │      ├─ _select_query_action()    选 action          │
  │      ├─ where eq/in → params      参数映射           │
  │      └─ → ApiExecTask                               │
  │                                                     │
  │  5c. 策略 B — 两阶段跨源执行                          │
  │      ├─ Phase 1：策略 A 查主对象（同源 JOIN 可下推）   │
  │      ├─ Phase 2：逐跳策略 A 查关联对象                │
  │      └─ MemoryMerger.left_join()  内存合并           │
  └──────────────────────┬──────────────────────────────┘
                         ▼
               Executor.run()（已有，不动）
               SqlExecTask → SqlExecutor → connector.execute()
               ApiExecTask → ApiExecutor
```

### 1.6 核心数据结构流转

```
OQL JSON
    │  object_type → OntologyClass（source_type / datasource_alias / fields）
    │  select / where / group_by / metrics / include_links / order_by / limit / offset
    ▼
[翻译层 — oql/adapter.py]
    │  field_map: dict[str, str]     {field_code → physical_column}
    │  where_sql: str                SQL WHERE 片段
    │  where_params: list            参数绑定列表（Hive 时为空，值已内联）
    │  join_sql: str                 LEFT JOIN 片段（同源 include_links）
    │  select_cols: list[str]        SELECT 列表达式（含 t.col AS alias）
    ▼
SqlExecTask(datasource_alias, sql_template)   — DB 对象
ApiExecTask(object_code, action_code, params) — API 对象
    ▼
[执行层 — 已有，不动]
Executor.run()
    SqlExecTask → SqlExecutor.execute() → connector.execute() → list[dict]
    ApiExecTask → ApiExecutor.execute()                       → list[dict]
    ▼
records: list[dict]   （策略 B 经 MemoryMerger.left_join() 合并后返回）
```

**列命名规范（全局一致）：**

| 来源 | 列名格式 | 示例 |
|------|---------|------|
| 主对象字段 | `field_code` | `enterprise_name` |
| 策略A 同源 JOIN 字段 | `{path}__{field_code}` | `manage_grid__grid_manager` |
| 策略B 内存合并字段 | `{path}__{field_code}` | `customer__customer_name` |

策略A（SQL JOIN）和策略B（内存合并）输出的列名格式完全相同，调用方无需感知底层走哪条路。

---

## 2. 功能设计

> 本章按执行层级组织：**原子翻译层**提供与策略无关的通用函数，**策略层**调用原子函数组合完整执行流，**路由层**在入口处判断分派。

### 2.0 模块层级总览

```
┌──────────────────────────────────────────────────────────────┐
│  2.5 路由层（OqlRouter）                                       │
│  · 判断单步 / Pipeline                                         │
│  · 判断单源 / 跨源                                             │
│  · Schema 校验 + 语义校验                                      │
└──────────┬──────────┬────────────────┬────────────────────────┘
           │          │                 │
┌──────────▼──┐  ┌────▼──────────┐  ┌──▼──────────────────────┐
│ 2.2 策略 A  │  │  2.3 策略 B   │  │     2.4 策略 C           │
│ 单源执行     │  │  跨源执行      │  │     Pipeline 执行        │
│ OqlAdapter  │  │  CrossSource  │  │     PipelineExecutor    │
│             │  │  Executor     │  │     + RefResolver        │
└──────┬──────┘  └────┬──────────┘  └──────────┬──────────────┘
       │               │  复用策略A               │ 每步降为策略A/B
       └───────────────┼──────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  2.1 原子翻译层                                                │
│  · 2.1.1 对象解析      · 2.1.2 字段解析（三级回退）             │
│  · 2.1.3 WHERE 条件翻译 · 2.1.4 同源 JOIN 翻译                │
│  · 2.1.5 聚合翻译       · 2.1.6 SQL 方言适配                  │
│  · 2.1.7 术语解析                                             │
└──────────────────────────────────────────────────────────────┘
```

---

### 2.1 原子翻译层

> **实现文件**：`oql/adapter.py`（新建）— module-level 函数，无状态，供 `OqlAdapter`、`CrossSourceExecutor` 共同调用。

原子翻译层包含所有与具体执行策略无关的纯翻译函数，三条策略均可调用此层。每个函数职责单一、独立可测。

#### 2.1.1 对象解析（Object Resolution）

`OntologyClass.source_type` 决定整条翻译路径：

| source_type | 翻译路径 | 执行任务 |
|-------------|---------|---------|
| `DB` | SQL 翻译 → `SqlExecTask` | `SqlExecutor.execute()` |
| `API` | 参数映射 → `ApiExecTask` | `ApiExecutor.execute()` |
| `KNOWLEDGE_BASE` | 不支持 QueryObjects，应建模为 DB/API 类型对象 | 报错引导 |

```python
def resolve_object(object_type: str, registry: OntologyRegistry) -> OntologyClass:
    cls = registry.get_class(object_type)
    if cls is None:
        raise OQLError("OQL_ERR_UNKNOWN_OBJECT_TYPE", object_type=object_type,
                       hint=registry.fuzzy_suggest(object_type))
    return cls

def route_by_source_type(cls: OntologyClass) -> str:
    if cls.source_type == "DB":
        return "sql"
    elif cls.source_type == "API":
        return "api"
    else:
        raise OQLError("OQL_ERR_UNSUPPORTED_SOURCE_TYPE",
                       message=f"对象 {cls.object_code} 不支持 QueryObjects")
```

**View 展开**：当 `object_type` 对应视图（View）时，视图在本体层已展开为对应的 `OntologyClass`（包含关联 JOIN 信息），翻译层透明处理，无需区分。

**表名解析**：

```python
def resolve_table(cls: OntologyClass) -> str:
    return cls.table_name or cls.object_code
```

---

#### 2.1.2 字段解析（Field Resolution）

**三级回退策略（保证 100% 解析成功）：**

```
Level 1: physical_mappings（多数据源映射）
         找到 source_type == 当前 DB 类型的条目 → 使用 entry.source_ref

Level 2: source_column（单数据源直接映射）
         OntologyField.source_column is not None → 使用 source_column

Level 3: field_code（兜底，100% 成功）
         → 使用 field_code 本身作为列名
```

```python
def resolve_column(field: OntologyField, db_type: str) -> str:
    for mapping in field.physical_mappings:
        if mapping.source_type.upper() == db_type.upper():
            return mapping.source_ref
    if field.source_column is not None:
        return field.source_column
    return field.field_code


def build_field_map(cls: OntologyClass, field_names: list[str], db_type: str) -> dict[str, str]:
    """批量解析 {字段名 → 物理列名}，字段不存在时抛 OQLError。"""
    field_index = {f.field_code: f for f in cls.fields}
    result, unknown = {}, []
    for name in field_names:
        if name not in field_index:
            unknown.append(name)
        else:
            result[name] = resolve_column(field_index[name], db_type)
    if unknown:
        raise OQLError("OQL_ERR_UNKNOWN_PROPERTY",
                       fields=unknown, hint=[f.field_code for f in cls.fields[:10]])
    return result


def find_primary_key(cls: OntologyClass, db_type: str) -> tuple[str, str]:
    """返回 (field_code, physical_column)，优先取 is_primary_key=True 的字段。"""
    for f in cls.fields:
        if f.is_primary_key:
            return f.field_code, resolve_column(f, db_type)
    if cls.fields:
        f = cls.fields[0]
        return f.field_code, resolve_column(f, db_type)
    raise OQLError("OQL_ERR_NO_PRIMARY_KEY",
                   message=f"对象 {cls.object_code} 未定义任何字段")
```

---

#### 2.1.3 WHERE 条件翻译

条件数组结构：

```
Condition = SimpleCondition | LogicCondition
SimpleCondition = { field: str, op: str, value: any }
LogicCondition  = { logic: "or", conditions: Condition[] }
                | { logic: "not", condition: Condition }
```

根节点条件间默认 AND。

**操作符对照表：**

| `op` | SQL 翻译 | `value` 类型 |
|------|----------|-------------|
| `eq` | `= ?` | 标量 |
| `ne` | `<> ?` | 标量 |
| `gt` / `gte` / `lt` / `lte` | `>` / `>=` / `<` / `<=` | 数值/日期 |
| `in` | `IN (...)` | 数组（空时翻译为 `1=0`） |
| `nin` | `NOT IN (...)` | 数组（空时翻译为 `1=1`） |
| `like` | `LIKE ?` | string |
| `isNull` | `IS NULL` / `IS NOT NULL` | boolean |
| `between` | `BETWEEN ? AND ?` | `[min, max]` |
| `relativeDate` | 展开为绝对时间区间后转 `BETWEEN` | 时间表达式字符串 |

```python
def translate_conditions(conditions, field_map, db_type, params, quoting='"', is_having=False) -> str:
    """将条件数组翻译为 SQL 片段（不含 WHERE 关键字）。"""
    parts = []
    for cond in conditions:
        if "logic" in cond:
            parts.append(translate_logic_condition(cond, field_map, db_type, params, quoting, is_having))
        else:
            parts.append(translate_simple_condition(cond, field_map, db_type, params, quoting, is_having))
    return " AND ".join(f"({p})" for p in parts)


def translate_simple_condition(cond, field_map, db_type, params, quoting, is_having) -> str:
    field, op, value = cond["field"], cond["op"], cond.get("value")
    col_expr = field if is_having else f"{quoting}{field_map[field]}{quoting}"
    ph = "?" if db_type.upper() != "HIVE" else None

    if op == "eq":
        params.append(value); return f"{col_expr} = {ph or inline_value(value)}"
    elif op == "ne":
        params.append(value); return f"{col_expr} <> {ph or inline_value(value)}"
    elif op in ("gt", "gte", "lt", "lte"):
        sym = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
        params.append(value); return f"{col_expr} {sym} {ph or inline_value(value)}"
    elif op == "in":
        if not value: return "1=0"
        phs = ", ".join(ph or inline_value(v) for v in value)
        if ph: params.extend(value)
        return f"{col_expr} IN ({phs})"
    elif op == "nin":
        if not value: return "1=1"
        phs = ", ".join(ph or inline_value(v) for v in value)
        if ph: params.extend(value)
        return f"{col_expr} NOT IN ({phs})"
    elif op == "like":
        params.append(value); return f"{col_expr} LIKE {ph or inline_value(value)}"
    elif op == "isNull":
        return f"{col_expr} IS NULL" if value else f"{col_expr} IS NOT NULL"
    elif op == "between":
        lo, hi = value[0], value[1]
        if ph: params.extend([lo, hi]); return f"{col_expr} BETWEEN ? AND ?"
        return f"{col_expr} BETWEEN {inline_value(lo)} AND {inline_value(hi)}"
    elif op == "relativeDate":
        start, end = expand_relative_date(value)
        if ph: params.extend([start, end]); return f"{col_expr} BETWEEN ? AND ?"
        return f"{col_expr} BETWEEN {inline_value(start)} AND {inline_value(end)}"
    else:
        raise OQLError("OQL_ERR_INVALID_OPERATOR", op=op)


def translate_logic_condition(cond, field_map, db_type, params, quoting, is_having) -> str:
    _t = lambda c: (translate_simple_condition(c, field_map, db_type, params, quoting, is_having)
                    if "logic" not in c
                    else translate_logic_condition(c, field_map, db_type, params, quoting, is_having))
    logic = cond["logic"]
    if logic == "or":
        return " OR ".join(f"({_t(c)})" for c in cond["conditions"])
    elif logic == "not":
        return f"NOT ({_t(cond['condition'])})"
    raise OQLError("OQL_ERR_INVALID_OPERATOR", op=f"logic:{logic}")
```

---

#### 2.1.4 同源 JOIN 翻译（include_links）

> **作用范围**：仅在策略 A（单源执行）中调用。跨源 `include_links` 由策略 B 处理，不调用此函数。

```python
def resolve_include_links(include_links, root_cls, root_alias, registry, db_type) -> tuple[str, list[str]]:
    """
    将同源 include_links 翻译为 LEFT JOIN 片段和附加 SELECT 列。
    返回 (join_sql, extra_select_cols)
    列别名格式 "{path__field}"，与策略 B 内存合并的结果列名保持一致。
    """
    join_parts, select_cols = [], []
    generated_paths: dict[str, str] = {"": root_alias}

    for clause in include_links:
        path, select_fields = clause["path"], clause.get("select", [])
        path_segments = path.split(".")
        if len(path_segments) > 5:
            raise OQLError("OQL_ERR_LINK_TOO_DEEP", path=path, max_depth=5)

        current_prefix, current_alias, current_cls = "", root_alias, root_cls

        for segment in path_segments:
            parent_prefix  = current_prefix
            current_prefix = f"{parent_prefix}.{segment}" if parent_prefix else segment
            rel = find_relation(current_cls, segment, registry)
            if rel is None:
                raise OQLError("OQL_ERR_UNKNOWN_LINK", link=segment, from_object=current_cls.object_code)
            target_cls = registry.get_class(rel.target_class)

            if current_prefix in generated_paths:
                current_alias, current_cls = generated_paths[current_prefix], target_cls
                continue

            join_alias = f"_j{len(generated_paths)}"
            generated_paths[current_prefix] = join_alias

            on_parts = []
            for jk in rel.join_keys:
                # jk: {"source_field": "crew_id", "target_field": "id"}（均为 field_code）
                src_col = resolve_join_key_column(current_cls, jk["source_field"], db_type)
                tgt_col = resolve_join_key_column(target_cls, jk["target_field"], db_type)
                on_parts.append(
                    f"{generated_paths[parent_prefix]}.{src_col} = {join_alias}.{tgt_col}"
                )
            join_parts.append(
                f"LEFT JOIN {resolve_table(target_cls)} AS {join_alias} ON {' AND '.join(on_parts)}"
            )
            current_alias, current_cls = join_alias, target_cls

        col_prefix    = path.replace(".", "_")
        fields_to_sel = select_fields or [f.field_code for f in current_cls.fields]
        for field_name in fields_to_sel:
            field_obj = find_field(current_cls, field_name)
            if field_obj is None:
                raise OQLError("OQL_ERR_UNKNOWN_PROPERTY",
                               field=field_name, object=current_cls.object_code)
            select_cols.append(
                f'{current_alias}.{resolve_column(field_obj, db_type)} AS "{col_prefix}__{field_name}"'
            )

    return "\n".join(join_parts), select_cols
```

`OntologyRelation.join_keys` 结构：`[{"source_field": "crew_id", "target_field": "id"}]`，字段均为 field_code，需经 `resolve_column()` 转为物理列名。

---

#### 2.1.5 聚合翻译（group_by / metrics / having）

```python
def build_aggregate_sql(oql_params, cls, db_type, registry) -> tuple[str, list]:
    """构建聚合模式 SQL，返回 (sql_template, params)。"""
    quoting, table, alias, params = get_quoting(db_type), resolve_table(cls), "t", []
    select_parts = []

    for gb in oql_params.get("group_by", []):
        physical_col = resolve_field_physical(cls, gb["field"], db_type)
        if gb.get("granularity"):
            select_parts.append(
                f"{time_trunc_expr(f'{alias}.{physical_col}', gb['granularity'], db_type)} AS time_bucket"
            )
        else:
            select_parts.append(
                f"{alias}.{quoting}{physical_col}{quoting} AS {quoting}{gb['field']}{quoting}"
            )
    for metric in oql_params.get("metrics", []):
        select_parts.append(build_metric_expr(alias, metric, cls, db_type, quoting))

    where_clause = ""
    if oql_params.get("where"):
        field_map    = build_field_map_all(cls, db_type)
        where_clause = f"WHERE {translate_conditions(oql_params['where'], field_map, db_type, params, quoting)}"

    gb_exprs = []
    for gb in oql_params.get("group_by", []):
        physical_col = resolve_field_physical(cls, gb["field"], db_type)
        gb_exprs.append(
            time_trunc_expr(f"{alias}.{physical_col}", gb["granularity"], db_type) if gb.get("granularity")
            else f"{alias}.{quoting}{physical_col}{quoting}"
        )
    group_by_clause = f"GROUP BY {', '.join(gb_exprs)}" if gb_exprs else ""

    having_clause = ""
    if oql_params.get("having"):
        having_clause = f"HAVING {translate_conditions(oql_params['having'], {{}}, db_type, params, quoting, is_having=True)}"

    ob_parts = [
        f"{quoting}{ob['field']}{quoting} {ob.get('direction', 'asc').upper()}"
        for ob in oql_params.get("order_by", [])
    ]
    if oql_params.get("group_by") and any(gb.get("granularity") for gb in oql_params["group_by"]):
        if "time_bucket" not in [ob["field"] for ob in oql_params.get("order_by", [])]:
            ob_parts.append("time_bucket ASC")
    order_by_clause = f"ORDER BY {', '.join(ob_parts)}" if ob_parts else ""

    clauses = [
        f"SELECT {', '.join(select_parts)}", f"FROM {table} AS {alias}",
        where_clause, group_by_clause, having_clause, order_by_clause,
        build_limit_clause(oql_params.get("limit", 1000), None, db_type),
    ]
    return "\n".join(c for c in clauses if c), params


def build_metric_expr(alias, metric, cls, db_type, quoting) -> str:
    name, op, field = metric["name"], metric["op"], metric.get("field")
    name_q = f"{quoting}{name}{quoting}"
    if op == "count": return f"COUNT(*) AS {name_q}"
    col = f"{alias}.{quoting}{resolve_field_physical(cls, field, db_type)}{quoting}"
    mapping = {"count_distinct": f"COUNT(DISTINCT {col})", "sum": f"SUM({col})",
               "avg": f"AVG({col})", "max": f"MAX({col})", "min": f"MIN({col})"}
    if op not in mapping: raise OQLError("OQL_ERR_INVALID_OPERATOR", op=f"metric:{op}")
    return f"{mapping[op]} AS {name_q}"
```

**时间截断方言表（`time_trunc_expr`）：**

| granularity | MySQL | PostgreSQL / OpenGauss | Hive | ClickHouse | SQLite |
|-------------|-------|------------------------|------|-----------|--------|
| `day` | `DATE(col)` | `DATE_TRUNC('day',col)` | `TO_DATE(col)` | `toDate(col)` | `DATE(col)` |
| `week` | `DATE_FORMAT(col,'%Y-%u')` | `DATE_TRUNC('week',col)` | `DATE_FORMAT(col,'yyyy-ww')` | `toStartOfWeek(col)` | `strftime('%Y-%W',col)` |
| `month` | `DATE_FORMAT(col,'%Y-%m')` | `DATE_TRUNC('month',col)` | `DATE_FORMAT(col,'yyyy-MM')` | `toStartOfMonth(col)` | `strftime('%Y-%m',col)` |
| `quarter` | `CONCAT(YEAR(col),'-Q',QUARTER(col))` | `DATE_TRUNC('quarter',col)` | `CONCAT(YEAR(col),'-Q',CEIL(MONTH(col)/3.0))` | `toStartOfQuarter(col)` | `strftime('%Y',col)\|\|'-Q'\|\|((CAST(strftime('%m',col) AS INT)+2)/3)` |
| `year` | `YEAR(col)` | `DATE_TRUNC('year',col)` | `YEAR(col)` | `toStartOfYear(col)` | `strftime('%Y',col)` |

---

#### 2.1.6 SQL 方言适配

**方言特性矩阵：**

| 特性 | MySQL | PostgreSQL | OpenGauss | ClickHouse | Hive | SQLite |
|------|-------|-----------|-----------|-----------|------|--------|
| 列名引号 | `` ` `` | `"` | `"` | `` ` `` | `` ` `` | `"` |
| 参数化 | `?` | `%s` | `%s` | `%s` | ❌ | `?` |
| OFFSET | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |

```python
def get_quoting(db_type: str) -> str:
    return '"' if db_type.upper() in ("POSTGRESQL", "OPENGAUSS", "SQLITE") else '`'

def build_limit_clause(limit: int, offset: int | None, db_type: str) -> str:
    if db_type.upper() == "HIVE": return f"LIMIT {limit}"
    return f"LIMIT {limit} OFFSET {offset}" if offset else f"LIMIT {limit}"

def normalize_sql_params(sql: str, params: list, db_type: str) -> tuple[str, list]:
    """将 ? 占位符适配为目标数据库驱动格式。Hive 不应调用此函数。"""
    if db_type.upper() in ("POSTGRESQL", "OPENGAUSS", "CLICKHOUSE"):
        return sql.replace("?", "%s"), params
    return sql, params

def inline_value(value) -> str:
    """Hive 专用：安全内联值到 SQL（防注入）。"""
    if value is None:                   return "NULL"
    if isinstance(value, bool):         return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)): return str(value)
    if isinstance(value, str):          return f"'{value.replace(chr(39), chr(92)+chr(39))}'"
    if isinstance(value, (list, tuple)):return f"({', '.join(inline_value(v) for v in value)})"
    return f"'{str(value).replace(chr(39), chr(92)+chr(39))}'"

def get_db_type_from_datasource(datasource_alias: str, datasource_registry) -> str:
    """未知数据源类型时，回退 MYSQL（最兼容的方言）。"""
    ds = datasource_registry.get(datasource_alias)
    if ds is None or not ds.get("db_type"): return "MYSQL"
    return ds["db_type"].upper()
```

---

#### 2.1.7 术语解析（Term Resolution）

含 `term_set` 的字段，在 WHERE 条件翻译**之前**将业务名称解析为物理存储值。

| term_type | 解析方式 |
|-----------|---------|
| `DICT_TERM` | 查字典表，`term_set` 为字典编码，`term_field` 指定匹配列 |
| `LIST_TERM` | 查本体对象实例，从 `term_set` 对象中匹配 `term_field` |
| `ONTOLOGY_TERM` | 先 QueryObjects 查关联对象，再取 PK 列表 |

```python
def resolve_term_value(field: OntologyField, raw_value, term_resolver) -> any:
    """将业务名称转换为物理值。无 term_set 时直接返回原始值。"""
    if not field.term_set: return raw_value
    if isinstance(raw_value, list):
        return [term_resolver.resolve(field.term_set, field.term_type, field.term_field, v)
                for v in raw_value]
    return term_resolver.resolve(field.term_set, field.term_type, field.term_field, raw_value)


def preprocess_where_terms(conditions: list[dict], cls: OntologyClass, term_resolver) -> list[dict]:
    """预处理 where 条件，有 term_set 的字段值 → 物理值（在条件翻译之前调用）。"""
    field_index = {f.field_code: f for f in cls.fields}
    result = []
    for cond in conditions:
        if "logic" in cond:
            result.append(cond)
            continue
        field_obj = field_index.get(cond["field"])
        if field_obj and field_obj.term_set:
            result.append({**cond, "value": resolve_term_value(field_obj, cond.get("value"), term_resolver)})
        else:
            result.append(cond)
    return result
```

---

### 2.2 策略 A：单源执行（OqlAdapter）

> **实现文件**：`oql/adapter.py`（新建）— `OqlAdapter` 类定义在此文件，与原子翻译层函数共存。

**适用条件**：主对象为单个 DB 对象（含同源 `include_links`），或主对象为 API 对象（无关联）。

由 `oql/adapter.py` 实现，职责是将 OQL 参数组装为原子翻译层的调用序列，输出可执行任务。

#### 2.2.1 DB 对象执行流

```
OQL JSON（DB 对象，单源）
    │
    ├─ preprocess_where_terms()      术语预处理（§2.1.7）
    ├─ build_field_map()             字段解析（§2.1.2）
    ├─ [有 metrics] build_aggregate_sql()   聚合路径（§2.1.5）
    └─ [无 metrics] _build_list_sql()       列表路径
         ├─ translate_conditions()   WHERE 翻译（§2.1.3）
         └─ resolve_include_links()  同源 JOIN 翻译（§2.1.4）
    │
    ▼ normalize_sql_params()         占位符方言适配（§2.1.6）
    ▼
SqlExecTask → Executor.run() → SqlExecutor.execute() → connector.execute()
```

```python
class OqlAdapter:

    def translate(self, oql_params: dict, registry: OntologyRegistry,
                  term_resolver, db_type: str) -> SqlExecTask | ApiExecTask:
        cls = resolve_object(oql_params["object_type"], registry)
        if cls.source_type == "API":
            return self.translate_api(oql_params, cls)
        return self.translate_db(oql_params, cls, db_type, registry, term_resolver)

    def translate_db(self, oql_params, cls, db_type, registry, term_resolver) -> SqlExecTask:
        where = preprocess_where_terms(oql_params.get("where", []), cls, term_resolver)
        all_fields = list({
            *oql_params.get("select", []),
            *[c["field"] for c in where if "logic" not in c],
            *[gb["field"] for gb in oql_params.get("group_by", [])],
            *[ob["field"] for ob in oql_params.get("order_by", [])],
        })
        field_map = build_field_map(cls, all_fields, db_type)
        if oql_params.get("metrics"):
            sql, params = build_aggregate_sql(oql_params, cls, db_type, registry)
        else:
            sql, params = self._build_list_sql(oql_params, cls, db_type, registry, field_map, where)
        sql, params = normalize_sql_params(sql, params, db_type)
        return SqlExecTask(datasource_alias=cls.datasource_alias, sql_template=sql, params=params)

    def _build_list_sql(self, oql_params, cls, db_type, registry, field_map, where):
        quoting = get_quoting(db_type)
        table, alias, params = resolve_table(cls), "t", []
        select_fields = oql_params.get("select") or list(field_map.keys())
        select_cols = [
            f"{alias}.{quoting}{field_map[f]}{quoting} AS {quoting}{f}{quoting}"
            for f in select_fields
        ]
        join_sql, extra_cols = resolve_include_links(
            oql_params.get("include_links", []), cls, alias, registry, db_type
        )
        select_cols += extra_cols
        where_clause = (f"WHERE {translate_conditions(where, field_map, db_type, params, quoting)}"
                        if where else "")
        ob_parts = [
            f"{quoting}{field_map[ob['field']]}{quoting} {ob.get('direction','asc').upper()}"
            for ob in oql_params.get("order_by", [])
        ]
        from_clause = f"FROM {table} AS {alias}"
        if join_sql: from_clause += f"\n{join_sql}"
        clauses = [
            f"SELECT {', '.join(select_cols)}", from_clause, where_clause,
            f"ORDER BY {', '.join(ob_parts)}" if ob_parts else "",
            build_limit_clause(oql_params.get("limit", 100), oql_params.get("offset"), db_type),
        ]
        return "\n".join(c for c in clauses if c), params
```

#### 2.2.2 API 对象执行流

WHERE 条件仅支持 `eq` / `in`，其他操作符记录 warning 后跳过，不报错。`order_by` 在 action IN 参数中有对应字段时注入，否则静默忽略。

```python
import logging
logger = logging.getLogger(__name__)

    def translate_api(self, oql_params: dict, cls: OntologyClass) -> ApiExecTask:
        select = oql_params.get("select", [])
        action = self._select_query_action(cls, select)
        in_codes = {p.param_code for p in action.params if p.direction == "IN"}

        params: dict = {}

        # WHERE 条件：仅映射 eq/in，其余操作符附 warning 后跳过
        _UNSUPPORTED_OPS: set[str] = set()
        for cond in oql_params.get("where", []):
            if "logic" in cond:
                continue
            if cond["op"] in ("eq", "in"):
                params[cond["field"]] = cond["value"]
            else:
                _UNSUPPORTED_OPS.add(cond["op"])
        if _UNSUPPORTED_OPS:
            logger.warning(
                "OQL translate_api: 对象 %s 的 WHERE 条件含不支持的操作符 %s，已跳过。"
                "API 对象 WHERE 仅支持 eq/in。",
                cls.object_code, _UNSUPPORTED_OPS,
            )

        # order_by：检测 action IN 参数是否支持排序，支持则注入
        for ob in oql_params.get("order_by", []):
            # 约定：排序方向参数名为 sort_by 或 order_by，字段名参数名即字段本身
            sort_param = next(
                (code for code in ("sort_by", "order_by") if code in in_codes), None
            )
            if sort_param:
                direction = ob.get("direction", "asc").upper()
                params[sort_param] = f"{ob['field']} {direction}"
            else:
                logger.debug(
                    "OQL translate_api: 对象 %s 的 action %s 不支持排序参数，order_by 已忽略。",
                    cls.object_code, action.action_code,
                )
            break  # API action 通常只接受单一排序参数，取第一条

        # limit / offset
        if "limit"  in in_codes: params["limit"]  = oql_params.get("limit", 100)
        if "offset" in in_codes: params["offset"] = oql_params.get("offset", 0)

        return ApiExecTask(object_code=cls.object_code, action_code=action.action_code,
                           params=params, output_ref=oql_params.get("output_ref", ""))

    @staticmethod
    def _select_query_action(cls: OntologyClass, select: list[str]) -> OntologyAction:
        """
        选取能覆盖 select 所有字段的 query action。
        1. 优先选 OUT 参数完全覆盖 select 的 action。
        2. 无精确匹配时回退到第一个 query action，并校验 select 中字段均在其 OUT 参数内。
        3. select 为空时直接取第一个 query action（不校验）。
        """
        query_actions = [a for a in cls.actions if a.action_type == "query"]
        if not query_actions:
            raise OQLError("OQL_ERR_NO_QUERY_ACTION",
                           message=f"API 对象 {cls.object_code} 未定义 query 类型 action")
        if not select:
            return query_actions[0]

        out_codes = lambda a: {p.param_code for p in a.params if p.direction == "OUT"}
        for action in query_actions:
            if all(f in out_codes(action) for f in select):
                return action

        # 回退：取第一个 action，但校验字段存在性（提前暴露错误）
        fallback = query_actions[0]
        available = out_codes(fallback)
        missing = [f for f in select if f not in available]
        if missing:
            raise OQLError(
                "OQL_ERR_UNKNOWN_PROPERTY",
                fields=missing,
                object=cls.object_code,
                hint=f"对象 {cls.object_code} 可用输出字段：{sorted(available)}",
            )
        return fallback
```

**API 对象约束：**

| 约束 | 说明 |
|------|------|
| WHERE 操作符 | 仅支持 `eq` / `in`；其余操作符记录 `logger.warning` 后跳过，不报错 |
| include_links | 不支持（API 主对象无 JOIN 语义，路由层前置拦截） |
| 聚合（metrics） | 不支持，路由层提前失败（`OQL_ERR_UNSUPPORTED_OPERATION`） |
| order_by | action IN 参数含 `sort_by`/`order_by` 时注入第一条；否则 `logger.debug` 忽略 |
| select 字段校验 | 选定 action 后校验 select 字段全部在 OUT 参数内；不满足则报 `OQL_ERR_UNKNOWN_PROPERTY` |

---

### 2.3 策略 B：跨源执行（CrossSourceExecutor）

> **实现文件**：
> - `oql/cross_source_executor.py`（新建）— `classify_include_links()` 函数 + `CrossSourceExecutor` 类
> - `oql/memory_merger.py`（新建）— `MemoryMerger` 类（独立文件，便于单独测试）

**适用条件**：`include_links` 中任一目标对象与主对象的 `datasource_alias` 不同，或目标对象 `source_type == API`。

无法下推 SQL JOIN，改为两阶段查询 + 内存合并。由 `oql/cross_source_executor.py` + `oql/memory_merger.py` 实现。

#### 2.3.1 跨源分类（classify_include_links）

将 `include_links` 分为同源组（可下推 SQL JOIN）和跨源组（需两阶段执行），支持两者混合。

```python
def classify_include_links(include_links, root_cls, registry) -> tuple[list[dict], list[dict]]:
    """
    返回 (same_source_links, cross_source_links)。
    同源：路径所有跳的目标 source_type==DB 且 datasource_alias 与主对象相同。
    跨源：任一跳的目标 source_type==API，或 datasource_alias 不同。

    注意：多跳路径（如 "A.B.C"）需要逐跳检查，任一跳跨源则整条路径归为跨源组。
    当前实现仅检查第一跳（简化版，适用于绝大多数业务场景）。
    如需完整多跳跨源检测，请用 _all_hops_same_source() 替换。
    """
    same, cross = [], []
    for clause in include_links:
        first_hop  = clause["path"].split(".")[0]
        rel        = registry.get_relation(root_cls.object_code, first_hop)
        target_cls = registry.get_class(rel.target_class)
        if (target_cls.source_type == "DB"
                and target_cls.datasource_alias == root_cls.datasource_alias):
            same.append(clause)
        else:
            cross.append(clause)
    return same, cross


def _all_hops_same_source(path: str, root_cls, registry) -> bool:
    """
    完整多跳同源检查：逐跳验证每个目标对象均为同源 DB。
    当 include_links 路径包含 3+ 跳且中间跳可能跨源时使用。
    """
    current_cls = root_cls
    for segment in path.split("."):
        rel = registry.get_relation(current_cls.object_code, segment)
        if rel is None:
            return False   # 关系不存在，由 resolve_include_links 报 OQL_ERR_UNKNOWN_LINK
        target_cls = registry.get_class(rel.target_class)
        if (target_cls.source_type != "DB"
                or target_cls.datasource_alias != root_cls.datasource_alias):
            return False
        current_cls = target_cls
    return True
```

#### 2.3.2 两阶段执行

```python
class CrossSourceExecutor:
    def execute(self, oql_params, registry, term_resolver, executor, datasource_registry) -> list[dict]:
        root_cls = resolve_object(oql_params["object_type"], registry)
        same_links, cross_links = classify_include_links(
            oql_params.get("include_links", []), root_cls, registry
        )

        # Phase 1：查主对象
        # · DB 主对象：同源 include_links 可一并下推 SQL JOIN
        # · API 主对象：same_links 必为空（路由层已前置拦截 API+include_links 的组合），
        #   直接走 translate_api
        phase1_oql = {**oql_params, "include_links": same_links}
        adapter    = OqlAdapter()
        if root_cls.source_type == "DB":
            db_type   = get_db_type_from_datasource(root_cls.datasource_alias, datasource_registry)
            main_task = adapter.translate_db(phase1_oql, root_cls, db_type, registry, term_resolver)
        else:
            main_task = adapter.translate_api(phase1_oql, root_cls)
        main_records: list[dict] = executor.run(main_task)

        # Phase 2：逐条跨源 include_links，逐跳顺序执行
        for clause in cross_links:
            main_records = self._execute_cross_link(
                clause, main_records, root_cls, registry,
                term_resolver, executor, datasource_registry,
            )
        return main_records

    def _execute_cross_link(self, clause, main_records, root_cls, registry,
                             term_resolver, executor, datasource_registry) -> list[dict]:
        first_hop  = clause["path"].split(".")[0]
        rel        = registry.get_relation(root_cls.object_code, first_hop)
        target_cls = registry.get_class(rel.target_class)
        src_field  = rel.join_keys[0]["source_field"]   # 主表关联字段（field_code）
        tgt_field  = rel.join_keys[0]["target_field"]   # 目标表关联字段（field_code）

        # 从主表结果提取关联键值（去重，过滤 None）
        key_values = list(dict.fromkeys(
            r[src_field] for r in main_records if r.get(src_field) is not None
        ))
        if not key_values:
            return main_records   # 无匹配值，等价于空 LEFT JOIN（见 §3.4.1）

        # 关联键超 1000 条时分批查询（见 §3.4.2）
        sub_records = self._fetch_sub_records_batched(
            key_values, tgt_field, clause, target_cls,
            registry, term_resolver, executor, datasource_registry,
        )

        col_prefix = clause["path"].replace(".", "_")
        return MemoryMerger.left_join(
            main_records, sub_records,
            main_key=src_field, sub_key=tgt_field, col_prefix=col_prefix,
        )

    BATCH_SIZE = 1000

    def _fetch_sub_records_batched(self, key_values, tgt_field, clause, target_cls,
                                    registry, term_resolver, executor, datasource_registry) -> list[dict]:
        """关联键分批发起子查询，合并结果（防止单个 IN 超限）。"""
        all_sub: list[dict] = []
        adapter = OqlAdapter()
        for i in range(0, len(key_values), self.BATCH_SIZE):
            batch = key_values[i : i + self.BATCH_SIZE]
            sub_oql = {
                "object_type": target_cls.object_code,
                "select": clause.get("select", []),
                "where":  [{"field": tgt_field, "op": "in", "value": batch}],
                "limit":  min(len(batch) * 10, 10000),
            }
            if target_cls.source_type == "DB":
                tgt_db   = get_db_type_from_datasource(target_cls.datasource_alias, datasource_registry)
                sub_task = adapter.translate_db(sub_oql, target_cls, tgt_db, registry, term_resolver)
            else:
                sub_task = adapter.translate_api(sub_oql, target_cls)
            all_sub.extend(executor.run(sub_task))
        return all_sub
```

#### 2.3.3 内存合并（MemoryMerger）

```python
class MemoryMerger:
    @staticmethod
    def left_join(main, sub, main_key, sub_key, col_prefix) -> list[dict]:
        """
        内存 LEFT JOIN。
        列命名格式 "{col_prefix}__{field}"，与同源 JOIN SELECT 别名一致。
        一对多时，主表行展开为多行；无匹配时关联字段填 None。
        """
        sub_index: dict = {}
        for row in sub:
            sub_index.setdefault(row.get(sub_key), []).append(row)

        sub_fields = list(sub[0].keys()) if sub else []
        none_row   = {f"{col_prefix}__{k}": None for k in sub_fields if k != sub_key}

        result = []
        for main_row in main:
            matched = sub_index.get(main_row.get(main_key), [])
            if not matched:
                result.append({**main_row, **none_row})
            else:
                for sub_row in matched:
                    merged = dict(main_row)
                    for k, v in sub_row.items():
                        if k != sub_key: merged[f"{col_prefix}__{k}"] = v
                    result.append(merged)
        return result
```

**策略 B 约束：**

| 约束 | 说明 |
|------|------|
| 聚合 | 主表聚合可下推 DB；跨源关联字段不可参与聚合函数 |
| 多跳跨源 | 支持，逐跳顺序执行，每跳结果作为下一跳的 main_records |
| 大数据量 IN | 关联键超过 1000 时，自动分批拆分 IN 查询后合并 |
| API 关联对象 | 继承策略 A 的 API 约束（仅 eq/in） |
| 同源+跨源混合 | 同源部分下推 SQL JOIN，跨源部分内存合并，两者可并存 |

---

### 2.4 策略 C：Pipeline 执行（PipelineExecutor）

> **实现文件**：`oql/pipeline_executor.py`（新建）— `PipelineExecutor` 类 + `RefResolver` 类。

**适用条件**：OQL 顶层为数组（多步组合），步骤间通过 `$ref` 表达式传递结果。

由 `oql/pipeline_executor.py` 实现。

#### 2.4.1 步骤顺序执行

```python
class PipelineExecutor:
    def execute(self, steps, registry, term_resolver, executor, datasource_registry) -> dict[str, list[dict]]:
        """
        顺序执行每个 step，context 收集各步结果。
        返回全部步骤结果字典，调用方通常取最后一步。
        每步经 execute_single_step() 完整走策略 A 或策略 B 的路由。

        失败策略：某步失败时整个 Pipeline 立即终止并向上传播异常。
        （后续版本可按依赖图实现部分失败跳过，当前不支持。）
        """
        if len(steps) > 10:
            raise OQLError("OQL_ERR_PIPELINE_TOO_LONG",
                           message=f"Pipeline 最多支持 10 步，当前 {len(steps)} 步")
        context: dict[str, dict] = {}
        router = OqlRouter(registry)
        for step in steps:
            step_id = step["step_id"]
            try:
                resolved_params = RefResolver.resolve(step["parameters"], context)
            except OQLError as e:
                raise OQLError(
                    e.code, message=f"step '{step_id}' $ref 解析失败：{e.message}", detail=e.detail
                )
            try:
                records = router.execute_single_step(
                    resolved_params, term_resolver, executor, datasource_registry
                )
            except OQLError as e:
                raise OQLError(
                    e.code, message=f"step '{step_id}' 执行失败：{e.message}", detail=e.detail
                )
            context[step_id] = {"records": records}
        return context
```

#### 2.4.2 $ref 表达式解析（RefResolver）

**$ref 语法：**

| 表达式 | 含义 | 结果类型 |
|--------|------|---------|
| `{"$ref": "s1.result[*].机型"}` | 提取 s1 所有记录的"机型"列（去重，过滤 None） | list |
| `{"$ref": "s1.result[0].id"}` | 提取 s1 第一行的"id" | 标量 |

```python
import re

class RefResolver:
    @staticmethod
    def resolve(params, context) -> dict:
        """递归扫描 params，将所有 {"$ref": expr} 替换为实际值。"""
        return RefResolver._v(params, context)

    @staticmethod
    def _v(value, context):
        if isinstance(value, dict):
            if "$ref" in value and len(value) == 1:
                return RefResolver._eval(value["$ref"], context)
            return {k: RefResolver._v(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [RefResolver._v(item, context) for item in value]
        return value

    @staticmethod
    def _eval(expr: str, context: dict):
        m = re.fullmatch(r"(\w+)\.result\[(\*|\d+)\]\.(.+)", expr)
        if not m:
            raise OQLError("OQL_ERR_INVALID_REF", expr=expr,
                           hint="格式：{step_id}.result[*].{field} 或 {step_id}.result[N].{field}")
        step_id, index, field = m.group(1), m.group(2), m.group(3)
        if step_id not in context:
            raise OQLError("OQL_ERR_REF_STEP_NOT_FOUND", step_id=step_id,
                           hint=f"已执行步骤：{list(context.keys())}")
        records = context[step_id]["records"]
        if index == "*":
            return list(dict.fromkeys(r[field] for r in records if r.get(field) is not None))
        idx = int(index)
        if idx >= len(records):
            raise OQLError("OQL_ERR_REF_INDEX_OUT_OF_RANGE", step_id=step_id, index=idx)
        return records[idx].get(field)
```

**$ref 空列表处理**：`result[*].field` 为空列表时，`op:in value:[]` 翻译为 `1=0`，快速返回空结果，不报错（见 §2.1.3）。

**Pipeline 约束：**

| 约束 | 说明 |
|------|------|
| 依赖方向 | 只支持有序依赖（后步引用前步），天然禁止循环引用 |
| 最大步骤数 | 10 步，超出报 `OQL_ERR_PIPELINE_TOO_LONG` |
| 步骤内能力 | 每步完整支持策略 A 和策略 B 的全部能力 |
| 并行执行 | 当前不支持，后续可按依赖图拓扑排序优化 |

---

### 2.5 路由判断（OqlRouter）

> **实现文件**：`oql/router.py`（新建）— `OqlRouter` 类 + `_handle_hive_offset()` 辅助函数。  
> 对外暴露的唯一入口是 `OqlRouter.route()`，由 `oql/__init__.py` 统一导出。

**职责**：入口层，校验 OQL 后判断执行模式并分派到正确策略。由 `oql/router.py` 实现。

#### 2.5.1 校验 + 路由流水线

```
OQL JSON 入参
    │
    ▼ [1] JSON Schema 校验              route()
    │   jsonschema.validate(oql, OQL_SCHEMA)
    │   失败 → OQL_ERR_SCHEMA_INVALID
    │
    ▼ [2] 类型判断                       route()
    │   isinstance(oql, list) → Pipeline 模式 → 策略 C，结束
    │   否则 → execute_single_step()，继续
    │
    ▼ [3] 对象解析                       execute_single_step()
    │   resolve_object(object_type, registry)
    │   失败 → OQL_ERR_UNKNOWN_OBJECT_TYPE（附 fuzzy hint）
    │
    ▼ [4] 前置约束检查                   execute_single_step()
    │   · API 对象有 metrics      → OQL_ERR_UNSUPPORTED_OPERATION
    │   · API 对象有 include_links → OQL_ERR_UNSUPPORTED_OPERATION
    │     （API 主对象无 JOIN 语义，关联查询请以 DB 对象为主对象）
    │   · Hive 有 offset>0        → warning + offset 截断为 0
    │
    ▼ [5] include_links 分类             execute_single_step()
    │   classify_include_links() → same_links / cross_links
    │   cross_links 非空 → 策略 B（CrossSourceExecutor）
    │   否则            → 策略 A（OqlAdapter）
    │
    ▼ 返回 records
```

> `execute_single_step()` 封装了 [3]-[5] 的完整逻辑，由 `route()` 和 `PipelineExecutor` 共用，确保 Pipeline 步骤也能正确路由到策略 B。

#### 2.5.2 路由实现

```python
class OqlRouter:
    def __init__(self, registry: OntologyRegistry):
        self.registry = registry

    def route(self, oql, term_resolver, executor, datasource_registry) -> list[dict]:
        """外部唯一入口：先判断 Pipeline，再委托 execute_single_step。"""
        validate_oql_schema(oql)

        if isinstance(oql, list):
            return PipelineExecutor().execute(
                oql, self.registry, term_resolver, executor, datasource_registry
            )

        return self.execute_single_step(oql, term_resolver, executor, datasource_registry)

    def execute_single_step(self, oql_params, term_resolver, executor, datasource_registry) -> list[dict]:
        """
        策略 A / B 执行（供 route() 和 PipelineExecutor 共用）。
        包含完整的对象解析、前置约束检查、路由判断，确保 Pipeline 步骤也能走策略 B。
        """
        cls = resolve_object(oql_params["object_type"], self.registry)

        # 前置约束检查
        if cls.source_type == "API" and oql_params.get("metrics"):
            raise OQLError("OQL_ERR_UNSUPPORTED_OPERATION",
                           message=f"API 对象 {cls.object_code} 不支持聚合（metrics）")

        if cls.source_type == "API" and oql_params.get("include_links"):
            raise OQLError(
                "OQL_ERR_UNSUPPORTED_OPERATION",
                message=f"API 对象 {cls.object_code} 不支持 include_links（API 主对象无 JOIN 语义）。"
                        "如需关联查询，请以 DB 对象为主对象，将 API 对象作为 include_links 目标。",
            )

        oql_params = _handle_hive_offset(oql_params, cls.datasource_alias, datasource_registry)

        # 路由判断：有跨源 links → 策略 B，否则 → 策略 A
        _, cross_links = classify_include_links(
            oql_params.get("include_links", []), cls, self.registry
        )
        if cross_links:
            return CrossSourceExecutor().execute(
                oql_params, self.registry, term_resolver, executor, datasource_registry
            )

        db_type = get_db_type_from_datasource(cls.datasource_alias, datasource_registry)
        task = OqlAdapter().translate(oql_params, self.registry, term_resolver, db_type)
        return executor.run(task)


def _handle_hive_offset(oql_params: dict, datasource_alias: str, datasource_registry) -> dict:
    db_type = get_db_type_from_datasource(datasource_alias, datasource_registry)
    if db_type == "HIVE" and oql_params.get("offset", 0) > 0:
        logger.warning(
            "Hive 不支持 OFFSET，对象 %s 的 offset=%d 已截断为 0。",
            oql_params["object_type"], oql_params["offset"],
        )
        return {**oql_params, "offset": 0}
    return oql_params
```

---

## 2.6 响应格式转换工具（供调用方使用）

> **架构说明**：
> - `datacloud-data` 不部署独立的 HTTP API 服务
> - `datacloud-analysis` 通过**代码引用**方式调用 `OqlRouter.route()`，返回 `list[dict]`
> - 本章节提供的格式转换工具函数供调用方（如 `datacloud-analysis`）使用，将内部格式转换为 §2.2.8（本体推理引擎重构方案.md）定义的标准响应格式
> - 实际的 HTTP 接入由 `by-framework-python` 网关负责

### 2.6.1 调用方式示例

```python
# 在 datacloud-analysis 中
from datacloud_data_sdk.oql.router import OqlRouter
from datacloud_data_sdk.oql.response_formatter import format_oql_response, format_oql_error

try:
    router = OqlRouter(registry, term_resolver, executor, datasource_registry)
    records = router.route(oql_params)  # 返回 list[dict]
    
    # 使用格式转换工具
    response = format_oql_response(
        tool="QueryObjects",
        records=records,
        total=total,  # 需要调用方自行获取
        limit=oql_params.get("limit", 100),
        offset=oql_params.get("offset", 0)
    )
except OQLError as e:
    response = format_oql_error(e)
```

### 2.6.2 响应格式转换（成功）

`OqlRouter.route()` 返回 `list[dict]` 后，调用方使用此工具函数进行格式转换：

```python
def format_oql_response(tool: str, records: list[dict], total: int, limit: int, offset: int = 0) -> dict:
    """
    将 OqlRouter.route() 返回的 list[dict] 转换为标准响应格式。
    
    Args:
        tool: 工具名称（"QueryObjects" 或 "ExecuteAction"）
        records: OqlRouter.route() 返回的记录列表
        total: 总记录数（需要调用方通过 COUNT 查询或 API 元数据获取）
        limit: 分页大小
        offset: 分页偏移量
    
    Returns:
        符合 §2.2.8 标准的响应字典
    """
    if not records:
        return {"status": "success", "tool": tool,
                "result": {"columns": [], "rows": [], "total": total, "returned": 0}}
    columns = list(records[0].keys())
    rows = [[row.get(col) for col in columns] for row in records]
    return {
        "status": "success",
        "tool": tool,
        "result": {
            "columns": columns,
            "rows": rows,
            "total": total,
            "returned": len(rows),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_next": total > (offset + limit),
            },
        },
    }
```

> **`total` 的获取方式**：
> - **DB 对象**：调用方需执行附加的 `SELECT COUNT(*) FROM ... WHERE ...` 查询（复用同一 WHERE 条件，不含 LIMIT/OFFSET）
> - **API 对象**：若 API 响应中有 total 字段则直接使用，否则 `total = len(records)`

### 2.6.3 响应格式转换（错误）

```python
def format_oql_error(error: OQLError) -> dict:
    """
    将 OQLError 异常转换为标准错误响应格式。
    
    Args:
        error: OQLError 异常对象
    
    Returns:
        符合 §2.2.8 标准的错误响应字典
    """
    return {
        "status": "error",
        "error_code": error.code,
        "message": error.message,
        "detail": error.details,
    }
```

### 2.6.4 ExecuteAction 响应格式

`ExecuteAction` 不返回 `list[dict]`，而是每个 target 的执行状态字典。调用方可直接使用，无需额外转换：

```python
# ExecuteAction 的返回格式已符合标准，可直接返回
{
    "status": "success",
    "tool": "ExecuteAction",
    "result": {
        "CA123": "success",
        "CA456": {"status": "failed", "reason": "..."}
    }
}
```

### 2.6.5 工具函数实现位置

建议在 `datacloud-data` 中创建 `oql/response_formatter.py` 模块，提供以下导出函数：

```python
# datacloud_data_sdk/oql/response_formatter.py

from datacloud_data_sdk.oql.models import OQLError

def format_oql_response(tool: str, records: list[dict], total: int, limit: int, offset: int = 0) -> dict:
    """格式转换工具函数（见 §2.6.2）"""
    ...

def format_oql_error(error: OQLError) -> dict:
    """错误格式转换工具函数（见 §2.6.3）"""
    ...
```

---

## 3. 转化成功策略

> 所有场景被归为两种处理方式：
> - **提前失败（Fast Fail）**：OQL 语义不合法，报结构化 error + hint，LLM 可自修正后重试，不产生无效执行。
> - **降级兜底（Graceful Degrade）**：OQL 合法但运行环境有约束，自动适配，附 warning 或静默忽略，不中断执行。

### 3.0 成功率保障总览

| 场景 | 对象类型 | 处理方式 | 结果 |
|------|---------|---------|------|
| 对象 / 字段名不存在 | DB / API | 提前失败 + fuzzy hint | LLM 可自修正 |
| DB 字段无 physical_mappings | DB | source_column → field_code 三级回退 | 100% 解析 |
| 未知 db_type | DB | 降级为 MYSQL 方言 | 100% 生成 SQL |
| Hive 无参数化 | DB(Hive) | `inline_value` 安全内联值 | 100% 执行 |
| Hive 无 OFFSET | DB(Hive) | 截断为 0 并附 warning | 100% 执行 |
| 空 IN / NOT IN 条件 | DB | 翻译为 `1=0` / `1=1` | 100% 合法 SQL |
| 跨源关联键为空集 | DB（策略B） | 跳过子查询直接返回主表结果 | 100% 执行 |
| 大 IN 超 1000 条 | DB（策略B） | 自动分批拆分后合并 | 100% 执行 |
| API + metrics | API | 提前失败 + 明确错误 | LLM 可自修正 |
| API + include_links | API | 提前失败 + 方向提示 | LLM 可自修正 |
| API select 字段不在 action OUT | API | 提前失败 + 可用字段 hint | LLM 可自修正 |
| API WHERE 不支持操作符（非 eq/in） | API | `logger.warning` 后跳过 | 降级执行，不崩溃 |
| API WHERE logic 条件（or/not） | API | `logger.warning` 后跳过 | 降级执行，不崩溃 |
| API order_by 但 action 无排序参数 | API | `logger.debug` 后静默忽略 | 降级执行，不崩溃 |
| API select 为空 | API | 取第一个 query action | 100% 执行 |

---

### 3.1 提前失败场景

提前失败的原则：**能在翻译阶段发现的语义错误，绝不推迟到执行阶段**。错误携带 hint，让 LLM 知道如何修正。

#### 3.1.1 DB 对象 — 对象 / 字段不存在

```python
# resolve_object()：对象不存在
raise OQLError(
    "OQL_ERR_UNKNOWN_OBJECT_TYPE",
    object_type=object_type,
    hint=registry.fuzzy_suggest(object_type),   # 相似对象名列表
)

# build_field_map()：字段不存在
raise OQLError(
    "OQL_ERR_UNKNOWN_PROPERTY",
    fields=unknown,
    hint=[f.field_code for f in cls.fields[:10]],  # 前 10 个可用字段
)
```

#### 3.1.2 API 对象 — 不支持的操作组合

在 `OqlRouter.route()` 中前置校验，翻译前拦截：

```python
# 1. API 对象 + metrics（API 不支持聚合）
if cls.source_type == "API" and oql_params.get("metrics"):
    raise OQLError(
        "OQL_ERR_UNSUPPORTED_OPERATION",
        message=f"对象 {cls.object_code} 为 API 类型，不支持聚合查询（metrics）。"
                "如需聚合，请在 API 数据接入后建立 DB 镜像对象。",
    )

# 2. API 主对象 + include_links（API 无 JOIN 语义）
if cls.source_type == "API" and oql_params.get("include_links"):
    raise OQLError(
        "OQL_ERR_UNSUPPORTED_OPERATION",
        message=f"对象 {cls.object_code} 为 API 类型，不支持 include_links。"
                "如需关联查询，请以 DB 对象为主对象，将 API 对象作为 include_links 目标。",
    )
```

在 `_select_query_action()` 中校验 select 字段：

```python
# 3. API select 字段不在任何 action 的 OUT 参数内
raise OQLError(
    "OQL_ERR_UNKNOWN_PROPERTY",
    fields=missing,
    object=cls.object_code,
    hint=f"对象 {cls.object_code} 可用输出字段：{sorted(available)}",
)
```

---

### 3.2 DB 对象降级兜底

#### 3.2.1 字段解析三级回退

`field_code` 兜底确保任何本体字段都能映射到物理列名，不会在字段解析阶段中断：

```
Level 1: physical_mappings → 匹配当前 db_type 的 source_ref
Level 2: source_column     → 直接映射
Level 3: field_code        → 兜底，100% 成功
```

#### 3.2.2 SQL 方言降级

未知数据源类型时，回退到兼容性最广的 MYSQL 方言，确保 SQL 总能生成：

```python
def get_db_type_from_datasource(datasource_alias, datasource_registry) -> str:
    ds = datasource_registry.get(datasource_alias)
    if ds is None or not ds.get("db_type"):
        return "MYSQL"   # 兜底方言
    return ds["db_type"].upper()
```

#### 3.2.3 Hive 无参数化兜底

Hive 不支持 `?` 占位符，所有值需内联到 SQL 字符串。`inline_value()` 对每类型做安全转义，防止 SQL 注入：

```python
def inline_value(value) -> str:
    if value is None:                    return "NULL"
    if isinstance(value, bool):          return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):  return str(value)
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(92)+chr(39))}'"   # 转义单引号
    if isinstance(value, (list, tuple)):
        return f"({', '.join(inline_value(v) for v in value)})"
    return f"'{str(value).replace(chr(39), chr(92)+chr(39))}'"
```

#### 3.2.4 Hive 无 OFFSET 兜底

Hive 不支持 `LIMIT n OFFSET m`，`offset > 0` 时截断并附 warning：

```python
def _handle_hive_offset(oql_params, datasource_alias, datasource_registry) -> dict:
    db_type = get_db_type_from_datasource(datasource_alias, datasource_registry)
    if db_type == "HIVE" and oql_params.get("offset", 0) > 0:
        logger.warning(
            "Hive 不支持 OFFSET，对象 %s 的 offset=%d 已截断为 0。",
            oql_params["object_type"], oql_params["offset"],
        )
        return {**oql_params, "offset": 0}
    return oql_params
```

#### 3.2.5 空 IN / NOT IN 条件兜底

```python
# translate_simple_condition() 中：
if op == "in"  and not value: return "1=0"   # 空集合 IN → 始终无结果
if op == "nin" and not value: return "1=1"   # 空集合 NOT IN → 不过滤
```

> 策略 B `$ref` 引用上步结果为空列表时，生成的子 OQL 含 `{"op":"in","value":[]}` 会命中此兜底，快速返回空结果而不是报错。

---

### 3.3 API 对象降级兜底

#### 3.3.1 WHERE 不支持的操作符 / logic 条件

API action 入参为键值对，无法表达复杂过滤，不支持的条件附 warning 后跳过，继续执行：

```python
# translate_api() 中：
for cond in oql_params.get("where", []):
    if "logic" in cond:
        # logic(or/not) 条件无法映射为 action 参数
        logger.warning(
            "OQL translate_api: 对象 %s 的 WHERE 含 logic 条件，API 不支持，已跳过。",
            cls.object_code,
        )
        continue
    if cond["op"] not in ("eq", "in"):
        logger.warning(
            "OQL translate_api: 对象 %s 的 WHERE 含不支持的操作符 %s，已跳过。",
            cls.object_code, cond["op"],
        )
        continue
    params[cond["field"]] = cond["value"]
```

#### 3.3.2 order_by 无对应排序参数

action IN 参数中没有 `sort_by`/`order_by` 时，静默忽略排序请求：

```python
sort_param = next((c for c in ("sort_by", "order_by") if c in in_codes), None)
if sort_param:
    params[sort_param] = f"{ob['field']} {ob.get('direction','asc').upper()}"
else:
    logger.debug("对象 %s action %s 不支持排序，order_by 已忽略。",
                 cls.object_code, action.action_code)
```

#### 3.3.3 select 为空时自动选 action

select 为空时无字段约束，直接取第一个 query action，无需校验：

```python
if not select:
    return query_actions[0]   # 不校验字段，取默认 action
```

---

### 3.4 跨源执行（策略 B）降级兜底

#### 3.4.1 关联键为空集

Phase 1 查出主表结果后，如果提取到的关联键值列表为空（主表无数据或关联字段全为 NULL），直接返回主表结果，不触发子查询：

```python
key_values = list(dict.fromkeys(
    r[src_field] for r in main_records if r.get(src_field) is not None
))
if not key_values:
    return main_records   # 无关联键，跳过子查询，相当于 LEFT JOIN 无匹配行
```

#### 3.4.2 大 IN 自动分批

关联键超过 1000 条时，拆分为多批次 IN 查询后合并，避免数据库单条 SQL 超限：

```python
BATCH_SIZE = 1000

def _execute_cross_link_batched(self, key_values, ...):
    all_sub = []
    for i in range(0, len(key_values), BATCH_SIZE):
        batch = key_values[i : i + BATCH_SIZE]
        sub_oql = {..., "where": [{"field": tgt_field, "op": "in", "value": batch}]}
        all_sub.extend(executor.run(...))
    return all_sub
```

> 分批阈值 `BATCH_SIZE=1000` 适用于大多数 DB；ClickHouse 可适当放大（建议 5000），通过数据源配置覆盖。

---

## 4. 完整示例

### 4.1 示例 1：MySQL 列表查询（含术语字段）

基于 e_commerce_demo 的 `ads_enterprise_analysis` 对象：

```
OntologyClass:
  object_code: ads_enterprise_analysis
  source_type: DB
  datasource_alias: yizhuang_brain
  table_name: ads_enterprise_analysis
  fields:
    - field_code: enterprise_name,       source_column: enterprise_name,       term_set: enterprise_list, term_type: LIST_TERM
    - field_code: business_status_name,  source_column: business_status_name,  term_set: business_status,  term_type: DICT_TERM
    - field_code: reg_capital,           source_column: reg_capital,           type: NUMBER
    - field_code: phy_grid_id,           source_column: phy_grid_id,           is_primary_key: true
```

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "ads_enterprise_analysis",
    "select": ["enterprise_name", "business_status_name", "reg_capital"],
    "where": [
      { "field": "business_status_name", "op": "in", "value": ["正常经营", "注销"] },
      { "field": "reg_capital", "op": "gte", "value": 1000000 }
    ],
    "order_by": [{ "field": "reg_capital", "direction": "desc" }],
    "limit": 20
  }
}
```

术语解析后（`business_status_name` 为 DICT_TERM，`正常经营` → `"1"`，`注销` → `"3"`）：

生成 SQL（MySQL，db_type=MYSQL）：
```sql
SELECT
    t.`enterprise_name` AS `enterprise_name`,
    t.`business_status_name` AS `business_status_name`,
    t.`reg_capital` AS `reg_capital`
FROM ads_enterprise_analysis AS t
WHERE
    (`business_status_name` IN (?, ?))
    AND (`reg_capital` >= ?)
ORDER BY `reg_capital` DESC
LIMIT 20
```
参数绑定：`["1", "3", 1000000]`

构建执行任务：
```python
SqlExecTask(
    datasource_alias="yizhuang_brain",
    sql_template=<上述 SQL>,
    output_ref="step_0",
)
```

---

### 4.2 示例 2：MySQL 聚合查询（含时间粒度）

**2a：普通分组聚合**

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "ads_enterprise_analysis",
    "metrics": [
      { "name": "企业数量", "op": "count" },
      { "name": "平均注册资本", "op": "avg", "field": "reg_capital" }
    ],
    "group_by": [
      { "field": "business_status_name" }
    ],
    "having": [
      { "field": "企业数量", "op": "gt", "value": 10 }
    ],
    "order_by": [{ "field": "企业数量", "direction": "desc" }]
  }
}
```

生成 SQL（MySQL）：
```sql
SELECT
    t.`business_status_name` AS `business_status_name`,
    COUNT(*) AS `企业数量`,
    AVG(t.`reg_capital`) AS `平均注册资本`
FROM ads_enterprise_analysis AS t
GROUP BY t.`business_status_name`
HAVING 企业数量 > ?
ORDER BY `企业数量` DESC
LIMIT 1000
```
参数绑定：`[10]`

> `HAVING` 中的字段直接使用 metric 名（`is_having=True` 时 `col_expr = field`，无引号），引用 SELECT 中的聚合别名。

**2b：时间粒度聚合（granularity）**

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "dws_order_detail",
    "metrics": [
      { "name": "订单数", "op": "count" },
      { "name": "总金额", "op": "sum", "field": "amount" }
    ],
    "group_by": [
      { "field": "create_time", "granularity": "month" }
    ],
    "order_by": [{ "field": "time_bucket", "direction": "asc" }]
  }
}
```

生成 SQL（MySQL）：
```sql
SELECT
    DATE_FORMAT(t.`create_time`, '%Y-%m') AS time_bucket,
    COUNT(*) AS `订单数`,
    SUM(t.`amount`) AS `总金额`
FROM dws_order_detail AS t
GROUP BY DATE_FORMAT(t.`create_time`, '%Y-%m')
ORDER BY time_bucket ASC
LIMIT 1000
```

---

### 4.3 示例 3：策略A：同源关联查询（include_links）

两个对象来自**同一数据源**，下推为 SQL LEFT JOIN（策略A）：

```
OntologyRelation:
  source_class: ads_enterprise_analysis
  target_class: ads_manage_grid_analysis
  datasource_alias: yizhuang_brain   # 与主对象相同 → 同源
  join_keys: [{"source_field": "manage_grid_id", "target_field": "manage_grid_id"}]
```

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "ads_enterprise_analysis",
    "select": ["enterprise_name", "reg_capital"],
    "include_links": [
      {
        "path": "manage_grid",
        "select": ["manage_grid_name", "grid_manager"]
      }
    ],
    "limit": 10
  }
}
```

`classify_include_links()` 判断 `manage_grid` 为同源 → 策略A，下推 SQL JOIN：

```sql
SELECT
    t.`enterprise_name` AS `enterprise_name`,
    t.`reg_capital` AS `reg_capital`,
    _j1.`manage_grid_name` AS `manage_grid__manage_grid_name`,
    _j1.`grid_manager` AS `manage_grid__grid_manager`
FROM ads_enterprise_analysis AS t
LEFT JOIN ads_manage_grid_analysis AS _j1
    ON t.`manage_grid_id` = _j1.`manage_grid_id`
LIMIT 10
```

---

### 4.4 示例 4：Hive 查询（无参数化，无 OFFSET）

```
OntologyClass:
  object_code: dws_order_detail
  source_type: DB
  datasource_alias: hive_warehouse   # db_type=HIVE
  table_name: dws_order_detail
  fields:
    - field_code: order_id,     source_column: order_id
    - field_code: amount,       source_column: amount
    - field_code: create_time,  source_column: create_time
    - field_code: status,       source_column: status
```

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "dws_order_detail",
    "select": ["order_id", "amount", "create_time"],
    "where": [
      { "field": "status", "op": "eq", "value": "PAID" },
      { "field": "create_time", "op": "relativeDate", "value": "this_month" }
    ],
    "limit": 1000,
    "offset": 500
  }
}
```

路由层处理：`db_type=HIVE` 且 `offset=500 > 0` → `_handle_hive_offset()` 截断为 0 并记录 warning。

生成 SQL（Hive）：
```sql
SELECT
    t.`order_id` AS `order_id`,
    t.`amount` AS `amount`,
    t.`create_time` AS `create_time`
FROM dws_order_detail AS t
WHERE
    (`status` = 'PAID')
    AND (`create_time` BETWEEN '2026-04-01 00:00:00' AND '2026-04-30 23:59:59')
LIMIT 1000
```
> Hive 无 `?` 参数绑定：值通过 `inline_value()` 安全内联（字符串加引号，数值直接输出）。`OFFSET` 不生成。

---

### 4.5 示例 5：API 对象单独查询

```
OntologyClass:
  object_code: crm_customer
  source_type: API
  actions:
    - action_code: query_customers
      action_type: query
      params:
        - {param_code: customer_id,  direction: IN}
        - {param_code: status,       direction: IN}
        - {param_code: sort_by,      direction: IN}
        - {param_code: limit,        direction: IN}
        - {param_code: customer_name, direction: OUT}
        - {param_code: credit_score,  direction: OUT}
```

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "crm_customer",
    "select": ["customer_name", "credit_score"],
    "where": [
      { "field": "status", "op": "eq", "value": "ACTIVE" },
      { "field": "credit_score", "op": "gte", "value": 80 }
    ],
    "order_by": [{ "field": "credit_score", "direction": "desc" }],
    "limit": 50
  }
}
```

翻译过程：
- `select` 字段全在 `query_customers` OUT 参数中 → 选中此 action
- `status eq ACTIVE` → 映射为 `params["status"] = "ACTIVE"`
- `credit_score gte 80` → 操作符 `gte` 不支持，`logger.warning` 后跳过
- `order_by credit_score desc` → `sort_by` 在 IN 参数中 → 注入 `params["sort_by"] = "credit_score DESC"`
- `limit` 在 IN 参数中 → 注入 `params["limit"] = 50`

生成执行任务：
```python
ApiExecTask(
    object_code="crm_customer",
    action_code="query_customers",
    params={
        "status": "ACTIVE",
        "sort_by": "credit_score DESC",
        "limit": 50,
    },
    output_ref="step_0",
)
```
> `credit_score gte 80` 被跳过不等于错误，执行结果是"ACTIVE 状态的客户按信用分排序前50条"，只是少了信用分下限过滤，调用方会收到 warning 日志。

---

### 4.6 示例 6：策略B：跨源查询（DB 主对象 + API 关联对象）

主对象来自 MySQL，关联对象来自 API，无法下推 SQL JOIN → 策略B 两阶段执行：

```
OntologyClass (主):
  object_code: order_record
  source_type: DB
  datasource_alias: erp_db   # MySQL

OntologyClass (关联):
  object_code: crm_customer
  source_type: API

OntologyRelation:
  source_class: order_record
  target_class: crm_customer
  join_keys: [{"source_field": "customer_id", "target_field": "customer_id"}]
```

OQL 输入：
```json
{
  "tool": "QueryObjects",
  "parameters": {
    "object_type": "order_record",
    "select": ["order_id", "amount", "customer_id"],
    "include_links": [
      {
        "path": "customer",
        "select": ["customer_name", "credit_score"]
      }
    ],
    "where": [
      { "field": "amount", "op": "gte", "value": 1000 }
    ],
    "limit": 20
  }
}
```

**Phase 1**：`classify_include_links()` 判断 `customer` 为跨源（API 对象）→ 策略B。
查主对象（DB），生成 SQL：

```sql
SELECT
    t.`order_id` AS `order_id`,
    t.`amount` AS `amount`,
    t.`customer_id` AS `customer_id`
FROM order_record AS t
WHERE (`amount` >= ?)
LIMIT 20
```
参数绑定：`[1000]`，返回主表记录 `main_records`（20 条）。

**Phase 2**：提取关联键 → 查 API 子对象 → 内存 LEFT JOIN：

```python
# 提取主表 customer_id 去重列表
key_values = ["C001", "C002", "C005", ...]   # 最多 20 个

# 构造子查询 OQL（向 API 发起）
sub_oql = {
    "object_type": "crm_customer",
    "select": ["customer_name", "credit_score"],
    "where": [{"field": "customer_id", "op": "in", "value": key_values}],
    "limit": 200,
}
# sub_records = [{"customer_id": "C001", "customer_name": "张三", "credit_score": 92}, ...]

# MemoryMerger.left_join：列前缀 = "customer"
# 结果列名：customer__customer_name, customer__credit_score
```

最终返回结果示例：
```python
[
    {
        "order_id": "ORD001", "amount": 1500, "customer_id": "C001",
        "customer__customer_name": "张三", "customer__credit_score": 92,
    },
    {
        "order_id": "ORD002", "amount": 2000, "customer_id": "C999",
        "customer__customer_name": None,   # 无匹配，LEFT JOIN 填 None
        "customer__credit_score": None,
    },
    ...
]
```

---

### 4.7 示例 7：策略C：Pipeline 查询（$ref 跨步引用）

OQL 顶层为数组，步骤间通过 `$ref` 传递结果：

```json
[
  {
    "step_id": "s1",
    "parameters": {
      "object_type": "flight_delay",
      "select": ["flight_no", "delay_minutes"],
      "where": [
        { "field": "route", "op": "eq", "value": "PEK-SHA" },
        { "field": "delay_minutes", "op": "gte", "value": 60 }
      ],
      "limit": 50
    }
  },
  {
    "step_id": "s2",
    "parameters": {
      "object_type": "passenger_ticket",
      "select": ["passenger_name", "contact", "flight_no"],
      "where": [
        {
          "field": "flight_no",
          "op": "in",
          "value": { "$ref": "s1.result[*].flight_no" }
        }
      ],
      "limit": 500
    }
  }
]
```

执行过程：

```
PipelineExecutor.execute():
    Step s1：
        resolved_params = s1.parameters（无 $ref，原样执行）
        → SqlExecTask → 查 flight_delay
        → context["s1"] = {"records": [
              {"flight_no": "CA101", "delay_minutes": 90},
              {"flight_no": "MU202", "delay_minutes": 120},
          ]}

    Step s2：
        RefResolver.resolve(s2.parameters, context)
            → $ref "s1.result[*].flight_no"
            → ["CA101", "MU202"]   # 去重、过滤 None
        resolved_params["where"][0]["value"] = ["CA101", "MU202"]
        → SqlExecTask（WHERE flight_no IN (?, ?)）→ 查 passenger_ticket
        → context["s2"] = {"records": [...]}
```

> 若 s1 返回空结果，`$ref` 解析为 `[]`，s2 的 WHERE `IN ([])` → 翻译为 `1=0`（§3.2.5 兜底），s2 快速返回空集，整个 Pipeline 不报错。
