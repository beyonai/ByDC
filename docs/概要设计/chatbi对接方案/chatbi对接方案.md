# chatbi对接方案

## 需求描述
1.D:\data\code\baiying\by-datacloud\examples\chatbi_demo\demo_normal.py
在config = OntologyAgentConfig 时增加一个 配置项参数sql_excute_url，该配置项替代DATACLOUD_SQL_SERVICE_URL 变量。用于接收本体sql执行器的地址。

2.agent.ask 方法，增加一个扩展参数，这个参数可以各类扩展变量，例如cookie，str，Array都可以往里面放。

3.当 OntologyAgentConfig的sql_excute_url 不为空时，执行sql使用以下类来执行sql
D:\data\code\baiying\by-datacloud\packages\datacloud-data\src\datacloud_data_sdk\sql_executor\connectors\http_sql_connector.py

4.D:\data\code\baiying\by-datacloud\packages\datacloud-data\src\datacloud_data_sdk\sql_executor\connectors\http_sql_connector.py
取消 DATACLOUD_SQL_SERVICE_URL 环境变量。

## 概要设计

### 1. 设计目标

将「SQL 执行后端地址」与「请求级扩展上下文」从全局环境变量/隐式约定收敛为**显式配置项**，使 chatbi 调用方能在不依赖进程环境的前提下：

1. 通过 `OntologyAgentConfig.sql_execute_url` 指定本体 SQL 执行器的 HTTP 地址。
2. 通过 `OntologyAgent.ask(..., extras=...)` 携带任意请求级扩展上下文（cookie / token / 业务字段等），由下游工具按需读取。

并据此清理 `DATACLOUD_SQL_SERVICE_URL` 环境变量这一隐式依赖。

### 2. 现状要点

| 关注点 | 现状 | 文件:行 |
|---|---|---|
| `OntologyAgentConfig` | dataclass，已有 8 个字段，**无 `sql_execute_url`** | `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py:105-116` |
| `OntologyAgent.ask()` | 仅接受固定参数（question / view_codes / object_codes / thread_id / user_code / session_id / locale），**无扩展通道** | `ontology_agent.py:243-253` |
| SQL connector 注册 | `ConnectorRegistry` 单例，`HTTP_SQL` 已注册到 `HttpSqlConnector` | `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/connector_registry.py:126` |
| `HttpSqlConnector.execute` | URL 来源：`os.environ["DATACLOUD_SQL_SERVICE_URL"]`（隐式依赖进程环境） | `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/connectors/http_sql_connector.py:26` |
| Connector 选型 | `DataSourceManager`：`config.datasource_id` 非空 ⇒ 强制 `HTTP_SQL`；否则按 `db_type` 选 | `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/data_source_manager.py:164-171` |
| 请求上下文 | `RequestContext` 已含 `gateway_context` / `workspace_dir` / `result_file_storage` 等，**无通用 `extras` 字段** | `packages/datacloud-data/src/datacloud_data_sdk/context.py:29-62` |

### 3. 总体方案

#### 3.1 数据流（端到端）

```
chatbi 调用方
   │
   │ ① OntologyAgentConfig(sql_execute_url="http://...")
   ▼
OntologyAgent.__init__
   │
   │ ② 透传到 LoaderConfig（新增同名字段）
   ▼
configure_loader → loader.configure(sql_execute_url=...)
   │
   ▼
DataSourceManager（读取 loader._config.sql_execute_url）
   │
   │ ③ sql_execute_url 非空 → 强制走 HTTP_SQL
   │    并把 URL 注入 HttpSqlConnector（构造时或 DataSourceConfig.config["url"]）
   ▼
HttpSqlConnector.execute（不再读 env，直接用注入的 URL）

────────── 请求级扩展（extras） ──────────

chatbi 调用方
   │
   │ ④ agent.ask(question, extras={"cookie": "...", ...})
   ▼
OntologyAgent._iter_events
   │
   │ ⑤ 透传到 InvocationContext(extras=...)
   ▼
RequestContext.extras（新增字段）  ←── 任意工具/connector 通过 get_current_context().extras 读取
```

#### 3.2 关键决策

**D-1：`sql_execute_url` 走配置而非 `extras`。**
SQL 执行器地址是部署级常量，绑定 Agent 实例生命周期；与请求级 `extras`（每次 ask 不同）应严格分层。

**D-2：`extras` 类型固定为 `dict[str, Any] | None`。**
不约束键名，由调用方与工具约定。SDK 内部不感知键含义，仅做透传。这允许 cookie、字符串、数组、嵌套字典等任意值放入。

**D-3：保留 `DATACLOUD_SQL_SERVICE_URL` 的删除是破坏性变更。**
现有依赖 env var 的部署需迁移到 `sql_execute_url`。需在 CHANGELOG 中明确告知。

**D-4：HttpSqlConnector 的 URL 注入采用「DataSourceConfig.config["url"]」路径，不引入新构造参数。**
原因：`ConnectorRegistry.get(db_type)(config)` 是统一签名，所有 connector 通过 `DataSourceConfig` 获取自身配置，保持一致性。`DataSourceManager` 在选定 `HTTP_SQL` 时把 `sql_execute_url` 写入 `config.config["url"]`，`HttpSqlConnector.execute` 改读 `self.config.config["url"]`。

**D-5：选型规则增强。**
`DataSourceManager`：`loader._config.sql_execute_url` 非空时**优先于 `db_type`** 选择 `HTTP_SQL`；同时仍保留 `config.datasource_id` 非空 → `HTTP_SQL` 的现有规则。两者可以并存。

#### 3.3 影响面

| 模块 | 改动类型 |
|---|---|
| `ontology_agent.py::OntologyAgentConfig` | 新增字段 `sql_execute_url: str \| None = None` |
| `ontology_agent.py::OntologyAgent.ask` | 新增参数 `extras: dict[str, Any] \| None = None` |
| `ontology_agent.py::OntologyAgent._iter_events` | 把 `extras` 透传到 `InvocationContext` |
| `datacloud_data_sdk/context.py::RequestContext` | 新增字段 `extras: dict[str, Any] \| None = None` |
| `datacloud_data_sdk/context.py::InvocationContext.__init__` | 接受 `extras` kwarg |
| `datacloud_data_sdk/ontology/loader.py::LoaderConfig` | 新增字段 `sql_execute_url: str \| None = None`，并暴露 `loader.sql_execute_url` 公有属性 |
| `tools/ontology_tool_loader.py::configure_loader` | 增加 `sql_execute_url` 参数透传 |
| `sql_executor/models.py::DataSourceConfig` | 新增字段 `endpoint_url: str = ""`（HTTP_SQL 后端地址；与既有 HTTP 专用字段 `datasource_id` 同模式） |
| `sql_executor/data_source_manager.py::DataSourceManager` | 持有 `sql_execute_url` 引用；连接器选择规则增强；为 `HTTP_SQL` 用 `dataclasses.replace` 注入 `endpoint_url` 到 config 副本 |
| `sql_executor/connectors/http_sql_connector.py::HttpSqlConnector.execute` | 改从 `self.config.endpoint_url` 读取地址；删除 `os.environ.get("DATACLOUD_SQL_SERVICE_URL")` |
| `sql_executor/connectors/http_sql_connector.py::HttpSqlConnector._build_headers` | cookie 取值优先级改为 `ctx.extras["cookie"] > ctx.cookie`，承接 chatbi 通过 `extras` 传入的 cookie |
| `sql_executor/ontology/owl_parser.py::_parse_database_definition` | **前置修复**：`datasourceId` → `dbId`（与 OWL 实际写入对齐） |
| `examples/chatbi_demo/demo_normal.py` | 使用新配置项 `sql_execute_url` 构造 demo |
| `tests/datacloud_data/test_sql_executor.py` | 替换 mock env var 的两处用例为构造 `DataSourceConfig(endpoint_url=..., datasource_id=...)` 直接驱动 |

### 4. 兼容性策略

| 场景 | 行为 |
|---|---|
| 调用方未设置 `sql_execute_url` 且无 `datasource_id` | 维持原行为（按 `db_type` 走本地 connector） |
| 调用方未设置 `sql_execute_url` 但 `datasource_id` 非空 | **保留现有 HTTP 强制规则**，但 URL 必须从 `DataSourceConfig.endpoint_url` 读取——若空则抛 `SqlExecutionError`（不再降级到 env） |
| 历史部署仍设置 `DATACLOUD_SQL_SERVICE_URL` | 不再生效，需迁移；CHANGELOG 与升级说明明确告知 |
| 调用方未传 `extras` | `RequestContext.extras = None`，下游无影响 |

### 5. 安全与可观测

- `extras` 内可能含敏感数据（cookie/token），不得进 `RequestContext.__repr__` —— 使用 `field(default=None, repr=False)`，与 `gateway_context`、`result_file_storage` 同模式。
- `HttpSqlConnector` 在 URL 缺失时记录 `logger.error` 并抛出明确异常，避免静默回退。
- 删除 env var 后，进程启动期不再做"env 必填检查"——改由首次执行 SQL 时校验 URL 配置。

### 6. 验收口径

1. `OntologyAgentConfig(sql_execute_url=...)` 可用，且 demo 跑通完整问答（端到端走 HTTP connector，命中真实 URL）。
2. `OntologyAgentConfig` 不传 `sql_execute_url` 时旧路径不破坏（按 db_type 选择，本地 connector 正常）。
3. `agent.ask(question, extras={...})` 透传后，工具/connector 内 `get_current_context().extras` 可拿到原值（含 dict / list / str 各类型）。
4. 全仓库 grep `DATACLOUD_SQL_SERVICE_URL` 命中数为 0（test 内的 monkeypatch 也清理）。
5. `uv run ruff format / check / mypy / pytest` 全绿。

## 详细设计

### 0. 前置 bug 修复（独立于本次 chatbi 改造，但必须先完成）

#### 0.1 问题

`OntologyLoader` 解析 OWL 时，对 `DatabaseDefinition` individual 读取 `datasource_id` 的字段名**与 OWL 实际写入字段名不一致**：

| 来源 | 字段名 |
|---|---|
| OWL 文件实际写入 | `<dbId>...</dbId>` |
| Parser 实际读取 | `datasourceId` |

参考样例：
- OWL：`byclaw-data/resource/object/EAppRptCoreIncomeNewtypeSumM/EAppRptCoreIncomeNewtypeSumM_dbsource.owl:15` 写 `<dbId>86994</dbId>`
- Parser：`packages/datacloud-data/src/datacloud_data_sdk/ontology/owl_parser.py:541` 读 `datasourceId`

**结果：** `ParsedDatasource.datasource_id` 永远 `None` → `DataSourceConfig.datasource_id` 永远 `None` → `HttpSqlConnector.execute` 第 31 行直接抛 `"HTTP SQL datasource_id is required"`，HTTP_SQL 路径在线上从未跑通。

#### 0.2 修复

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/ontology/owl_parser.py:541`

```python
# 改前
datasource_id_str = self._get_predicate_value(g, subject, "datasourceId")

# 改后
datasource_id_str = self._get_predicate_value(g, subject, "dbId")
```

**未受影响：**
- `http_sql_connector.py:35` 的 `"datasourceId": self.config.datasource_id` 是发给后端 HTTP 服务的 JSON payload key（接口协议），与 OWL 字段名无关，**保留不动**。
- `test_sql_executor.py` 中三处 `"datasourceId"` 也是 HTTP payload 断言，保留不动。

#### 0.3 范围

本修复独立于 chatbi 对接，但**必须先完成**——没有它跑不通后续的「验收 1」（HTTP_SQL 流程整体走通）。

### 1. 字段新增 / API 变更清单

#### 1.1 `OntologyAgentConfig`

**文件：** `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py`

```python
@dataclass
class OntologyAgentConfig:
    api_key: str
    model: str
    resource_path: str | Path
    base_url: str | None = None
    locale: str = "zh_CN"
    temperature: float = 0.7
    model_kwargs: dict[str, Any] | None = None
    result_file_storage: Any = None
    sql_execute_url: str | None = None   # ← 新增
```

#### 1.2 `OntologyAgent.ask` / `OntologyAgent.resume`

**文件：** `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py`

```python
def ask(
    self,
    question: str,
    *,
    view_codes: list[str] | None = None,
    object_codes: list[str] | None = None,
    thread_id: str | None = None,
    user_code: str | None = None,
    session_id: str | None = None,
    locale: str | None = None,
    extras: dict[str, Any] | None = None,   # ← 新增
) -> AsyncGenerator[OntologyAgentEvent, None]:
    ...

def resume(
    self,
    thread_id: str,
    user_input: str | ParadigmAnswer,
    *,
    view_codes: list[str] | None = None,
    object_codes: list[str] | None = None,
    user_code: str | None = None,
    session_id: str | None = None,
    extras: dict[str, Any] | None = None,   # ← 新增（与 ask 对称）
) -> AsyncGenerator[OntologyAgentEvent, None]:
    ...
```

#### 1.3 `RequestContext` / `InvocationContext`

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/context.py`

```python
@dataclass
class RequestContext:
    # ... 既有字段 ...
    extras: dict[str, Any] | None = field(default=None, repr=False)  # ← 新增
```

`InvocationContext.__init__` 增加 `extras` kwarg，写入 `RequestContext.extras`。

> 工具按用户决策直接通过 `get_current_context().extras` 访问，**SDK 不提供快捷读取 API**。

#### 1.4 `LoaderConfig` / `OntologyLoader`

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/ontology/loader.py`

```python
@dataclass
class LoaderConfig:
    # ... 既有字段 ...
    sql_execute_url: str | None = None   # ← 新增
```

`OntologyLoader` 暴露公有属性：
```python
@property
def sql_execute_url(self) -> str | None:
    """供 DataSourceManager 在选择 HTTP connector 时读取。"""
    return self._config.sql_execute_url
```

#### 1.5 `configure_loader`

**文件：** `packages/datacloud-analysis/src/datacloud_analysis/tools/ontology_tool_loader.py`

```python
def configure_loader(
    loader: Any,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
    model_kwargs: dict[str, Any] | None = None,
    csv_base_dir: str = "",
    sql_execution_mode: str = "internal",
    result_file_storage: Any = None,
    sql_execute_url: str | None = None,   # ← 新增
) -> None:
    ...
    loader.configure(
        plan_generator=plan_generator,
        term_loader=term_loader,
        csv_base_dir=csv_base_dir,
        sql_execution_mode=sql_execution_mode,
        result_file_storage=result_file_storage,
        sql_execute_url=sql_execute_url,   # ← 新增
    )
```

`OntologyAgent._build_loader` 调用处增加透传：`sql_execute_url=self._config.sql_execute_url`。

#### 1.6 `DataSourceConfig`

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/models.py`

```python
@dataclass
class DataSourceConfig:
    alias: str
    db_type: str
    # ... 既有字段 ...
    datasource_id: int | None = None
    endpoint_url: str = ""   # ← 新增；HTTP_SQL 后端地址
```

> 与既有 HTTP 专用字段 `datasource_id` 保持同样模式。本字段对非 HTTP connector 无意义。

#### 1.7 `DataSourceManager.get_connector`

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/data_source_manager.py`

修改 connector 选型与配置注入逻辑：

```python
def get_connector(self, alias: str) -> BaseSourceConnector:
    if alias in self._connectors:
        return _LoggingConnectorProxy(self._connectors[alias])

    config = self._configs.get(alias)
    if config is None and self._fallback_loader is not None:
        # ... 原 fallback 逻辑保持不变 ...
        ...
    if config is None:
        raise DataSourceUnavailableError(alias)

    # 选型规则：sql_execute_url 非空 OR datasource_id 非空 → HTTP_SQL
    sql_execute_url = getattr(self._fallback_loader, "sql_execute_url", None) if self._fallback_loader else None
    force_http = bool(sql_execute_url) or config.datasource_id is not None

    if force_http:
        connector_cls = ConnectorRegistry.get("HTTP_SQL")
        # 注入 endpoint_url 到 config 副本，避免污染原配置
        if sql_execute_url:
            config = dataclasses.replace(config, endpoint_url=sql_execute_url)
    else:
        connector_cls = ConnectorRegistry.get(config.db_type)

    connector = connector_cls(config)
    self._connectors[alias] = connector
    return _LoggingConnectorProxy(connector)
```

#### 1.8 `HttpSqlConnector`

**文件：** `packages/datacloud-data/src/datacloud_data_sdk/sql_executor/connectors/http_sql_connector.py`

修改 `execute`：

```python
async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    endpoint_url = self.config.endpoint_url
    if not endpoint_url:
        raise SqlExecutionError(
            self.config.alias, sql,
            "HTTP SQL endpoint_url is required (set via OntologyAgentConfig.sql_execute_url)"
        )
    if self.config.datasource_id is None:
        raise SqlExecutionError(self.config.alias, sql, "HTTP SQL datasource_id is required")
    # ... 后续逻辑不变 ...
```

同时修改 `_build_headers`，**让 `extras["cookie"]` 成为 cookie 的优先来源**：

```python
def _build_headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}

    try:
        ctx = get_current_context()
    except DatacloudError:
        return headers

    if ctx.token:
        headers["Authorization"] = f"Bearer {ctx.token}"
    if ctx.tenant_id:
        headers["X-Tenant-Id"] = ctx.tenant_id
    if ctx.user_id:
        headers["X-User-Id"] = ctx.user_id
    if ctx.session_id:
        headers["X-Session-Id"] = ctx.session_id
    if ctx.system_code:
        headers["X-System-Code"] = ctx.system_code

    # cookie 取值优先级：extras["cookie"] > RequestContext.cookie
    # chatbi 调用方应通过 agent.ask(extras={"cookie": "..."}) 传入；
    # 既有 byclaw-data 路径仍可使用 InvocationContext(cookie=...) 保持兼容。
    cookie = ctx.cookie
    if isinstance(ctx.extras, dict):
        extras_cookie = ctx.extras.get("cookie")
        if isinstance(extras_cookie, str) and extras_cookie:
            cookie = extras_cookie
    if cookie:
        headers["cookie"] = cookie

    return headers
```

**移除：**
- `import os`（不再使用）
- 第 26 行 `os.environ.get("DATACLOUD_SQL_SERVICE_URL")`

> **关于其他 header 字段（token / tenant_id / user_id / session_id / system_code）的取值策略：**
> 本次仅把 `cookie` 接入 `extras`，因为 chatbi 用例明确把 cookie 放进 `extras`。
> 其余字段沿用 `RequestContext` 顶级字段（`token` / `tenant_id` 等），由调用方通过 `InvocationContext(token=..., ...)` 注入或经 `_iter_events` 内已有路径填充。
> 如未来 chatbi 也需要从 `extras` 透传这些字段，按相同模式扩展即可（每个字段独立判断 `extras[<key>]` 优先）。

### 2. 数据流落地细节

#### 2.1 `sql_execute_url` 流转

```
OntologyAgentConfig.sql_execute_url
    │
    ▼ OntologyAgent._build_loader
configure_loader(..., sql_execute_url=<value>)
    │
    ▼ loader.configure(sql_execute_url=<value>)
LoaderConfig.sql_execute_url
    │
    ▼ loader.sql_execute_url  (公有属性)
DataSourceManager.get_connector → 检查 → 写入 DataSourceConfig.endpoint_url（副本）
    │
    ▼ HttpSqlConnector(config).execute → self.config.endpoint_url
真实 HTTP 请求
```

#### 2.2 `extras` 流转（含 cookie 落地点）

```
agent.ask(question, extras={"cookie": "JSESSIONID=xxx", "biz_token": [...]})
    │
    ▼ OntologyAgent._iter_events
ctx_container = SimpleNamespace(
    user_id=user_code or "",
    session_id=session_id or "",
    extras=extras,   ← 新增
)
configurable["gateway_context"] = ctx_container
    │
    ▼ tool_wrapper.dispatch_tool（已有 InvocationContext 装配点）
InvocationContext(
    user_id=...,
    session_id=...,
    gateway_context=gateway_context,
    workspace_dir=...,
    result_file_storage=...,
    extras=getattr(gateway_context, "extras", None),   ← 新增一行
)
    │
    ▼ 任意工具/connector
get_current_context().extras  → 原始 dict
                                │
                                │ ── 关键消费点：HttpSqlConnector._build_headers ──
                                ▼
                cookie = ctx.extras.get("cookie") or ctx.cookie
                if cookie: headers["cookie"] = cookie
                                │
                                ▼
        httpx.AsyncClient.post(endpoint_url, json=payload, headers=headers)
                                  携带最终 cookie 发起 SQL 服务调用
```

> `tool_wrapper.py:716-721` 已经是统一装配点（上次重构遗留），本次只在该处加一行从 `gateway_context` 中读出 `extras`。
>
> **cookie 取值优先级：** `ctx.extras["cookie"]`（chatbi 路径） > `ctx.cookie`（既有 byclaw-data 路径）。两者都为空则不发送 cookie header。

### 3. 需要删除的内容

| 位置 | 内容 | 原因 |
|---|---|---|
| `http_sql_connector.py:6` | `import os` | 不再使用 |
| `http_sql_connector.py:26-30` | `os.environ.get("DATACLOUD_SQL_SERVICE_URL")` 与对应错误信息 | 改为从 `config.endpoint_url` 读取 |
| `tests/datacloud_data/test_sql_executor.py:109-114` | `patch.dict("os.environ", {"DATACLOUD_SQL_SERVICE_URL": ...})` | 改为构造 `DataSourceConfig(endpoint_url=..., datasource_id=..., ...)` 直接驱动 |
| `tests/datacloud_data/test_sql_executor.py:222-224` | 同上 | 同上 |

### 4. 测试改写方案（test_sql_executor.py）

两处用例的改写模式一致，以 `:106-128` 段为例：

**改写前（依赖 env）：**
```python
with InvocationContext(token="token-1", ...):
    with patch.dict(
        "os.environ",
        {"DATACLOUD_SQL_SERVICE_URL": "http://localhost:8000/.../executeSql"},
    ):
        with patch("httpx.AsyncClient.post", mock_post):
            result = await executor.execute(...)
```

**改写后（用 config 驱动）：**
```python
# 在 fixture/setup 处构造 config 时直接带 endpoint_url
http_config = DataSourceConfig(
    alias="ds_http",
    db_type="HTTP_SQL",
    datasource_id=86039,
    endpoint_url="http://localhost:8000/knowledgeService/callDomainModel/executeSql",
)
manager = DataSourceManager({"ds_http": http_config})
# ...

with InvocationContext(token="token-1", ...):
    with patch("httpx.AsyncClient.post", mock_post):
        result = await executor.execute(...)
```

`mock_post.assert_awaited_once()` 与 headers 断言保持不变。

### 5. 不在本次范围

- Connector 注册新的 `HTTP_SQL_V2` 等；现有 `HTTP_SQL` 改造已足够。
- `extras` 的 schema 校验或键名约定；本次只做透传。
- `chatbi_demo/demo_normal.py` 之外的 examples 同步；调用方按需自行迁移。

---

## 验收用例

### 验收 1：`OntologyAgentConfig.sql_execute_url` 可注入

- **前置：** demo `examples/chatbi_demo/demo_normal.py` 构造 config 时传入 `sql_execute_url="http://test.example/api/sql"`。
- **执行：** 跑一次完整问答流程，触发任一 SQL 步骤。
- **观测点：** 通过 `unittest.mock.patch("httpx.AsyncClient.post")` 抓 HTTP 请求，断言其 URL 等于 `http://test.example/api/sql`。
- **预期：** ✅ 命中预期 URL；进程 env 中**不存在** `DATACLOUD_SQL_SERVICE_URL`。

### 验收 2：未传 `sql_execute_url` 不破坏本地路径

- **前置：** demo 不传 `sql_execute_url`；提供本体内 SQLite/MySQL 数据源（`datasource_id=None`）。
- **执行：** 触发一次 SQL 步骤。
- **预期：** ✅ 走本地 connector（按 `db_type` 选择），无 HTTP 请求；任意 `httpx.AsyncClient.post` 未被调用。

### 验收 3：`agent.ask(extras=...)` 正确透传至 `RequestContext`

- **前置：** 自定义一个 langchain `@tool`，函数体内读取 `get_current_context().extras` 并写入测试断言用的全局变量（或返回值）。
- **执行：** `await agent.ask("问题", extras={"cookie": "k=v", "biz": ["x", "y"], "nested": {"a": 1}})`。
- **预期：** ✅ 工具被调用时读到的 extras 与传入完全相等（含 dict / list / str 嵌套）。

### 验收 4：`HttpSqlConnector` 在 `endpoint_url` 缺失时清晰失败

- **前置：** 构造 `DataSourceConfig(db_type="HTTP_SQL", datasource_id=1, endpoint_url="")`。
- **执行：** 调用 `executor.execute(...)`。
- **预期：** ✅ 抛出 `SqlExecutionError`，message 包含「endpoint_url is required」与 `OntologyAgentConfig.sql_execute_url` 提示；**不再出现 `DATACLOUD_SQL_SERVICE_URL` 字样**。

### 验收 5：`DATACLOUD_SQL_SERVICE_URL` 全仓库零引用

- **执行命令：**
  ```powershell
  Select-String -Path . -Pattern "DATACLOUD_SQL_SERVICE_URL" -Recurse
  ```
- **预期：** ✅ 命中数 0（含源码 + 测试 + 配置文件 + 文档）。

### 验收 6：`test_sql_executor.py` 两个 HTTP 用例改写后通过

- **执行：** `uv run pytest packages/datacloud-data/tests/datacloud_data/test_sql_executor.py -v`
- **预期：** ✅ 全绿，**且没有 `patch.dict("os.environ", ...)`** 残留。

### 验收 7：静态检查与现有测试

```powershell
uv run ruff format packages
uv run ruff check packages
uv run python -m mypy packages/datacloud-data/src packages/datacloud-analysis/src
uv run pytest packages/
```

- **预期：** ✅ 全部通过；不引入新的 ruff/mypy warning。

### 验收 8：`extras` 不进 repr（敏感信息防护）

- **执行：**
  ```python
  ctx = RequestContext(extras={"cookie": "secret"})
  assert "cookie" not in repr(ctx)
  assert "secret" not in repr(ctx)
  ```
- **预期：** ✅ extras 字段不出现在 `repr` 输出中（与 `gateway_context` 同样使用 `repr=False`）。

### 验收 9：`extras["cookie"]` 端到端落入 HTTP 请求 header（chatbi 关键路径）

- **前置：**
  - `OntologyAgentConfig(sql_execute_url="http://test.example/api/sql")`
  - 准备一个含 `<dbId>` 的 OWL 数据源
  - mock `httpx.AsyncClient.post` 抓取实际请求
- **执行：**
  ```python
  await agent.ask(
      "查 X 报表",
      extras={"cookie": "JSESSIONID=abc123; bdp=k1"},
  )
  ```
- **预期：**
  - ✅ `mock_post.await_args.kwargs["headers"]["cookie"] == "JSESSIONID=abc123; bdp=k1"`
  - ✅ 同时 `kwargs["url"] == "http://test.example/api/sql"`（验收 1）
  - ✅ `kwargs["json"]["datasourceId"]` 来自 OWL `<dbId>` 解析值（验收 9 / 验收 10）

### 验收 10：cookie 取值优先级（extras > RequestContext.cookie）

- **场景 A：** 仅 `InvocationContext(cookie="legacy=1")`，未传 `extras`
  - 预期：`headers["cookie"] == "legacy=1"`（旧路径兼容）
- **场景 B：** 同时 `InvocationContext(cookie="legacy=1")` 与 `extras={"cookie": "new=2"}`
  - 预期：`headers["cookie"] == "new=2"`（extras 优先）
- **场景 C：** 仅 `extras={"cookie": ""}`（空字符串）
  - 预期：`headers["cookie"]` 不存在（空值不发送）；若同时有 `ctx.cookie="legacy=1"` 则取 legacy 值
- **场景 D：** `extras={"cookie": 12345}`（非字符串）
  - 预期：忽略 extras 值，回退到 `ctx.cookie`；记录 debug 日志或静默（实现自定）

### 验收 11：OWL `dbId` → `DataSourceConfig.datasource_id`（前置修复验证）

- **前置：** 加载一个含 `<dbId>86994</dbId>` 的 `_dbsource.owl`（如 `byclaw-data/resource/object/EAppRptCoreIncomeNewtypeSumM/EAppRptCoreIncomeNewtypeSumM_dbsource.owl`）。
- **执行：**
  ```python
  loader = OntologyLoader()
  loader.load_from_owl_resource_directory(<resource_dir>)
  # 通过 loader 暴露的接口读出对应数据源配置
  ds = loader._datasources["23_user_app_report"]   # 或经公有 API
  assert ds.datasource_id == 86994
  ```
- **预期：** ✅ `datasource_id` 正确解析为 `86994`（修复前为 `None`）。
- **辅助验证：**
  ```powershell
  Select-String -Path packages -Pattern '"datasourceId"' -Recurse |
    Where-Object { $_.Path -like "*owl_parser.py" }
  ```
  预期 0 命中（`owl_parser.py` 中 `datasourceId` 字面量已被替换为 `dbId`）。

