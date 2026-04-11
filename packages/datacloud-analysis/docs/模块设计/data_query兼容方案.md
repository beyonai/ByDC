# db_query 模式兼容方案

## 背景

系统通过环境变量 `ONTOLOGY_LOAD_MODE` 区分两种查询工具挂载模式：

| 模式 | 工具名格式 | 设计意图 |
|------|-----------|---------|
| `ontology_query` | `query_{code}` / `compute_{code}` | 细粒度查询 + 聚合计算，由 OntologyToolLoader 在运行时动态生成 |
| `db_query` | `data_query_{code}` | 每个对象/视图挂载一个统一查询工具，启动时静态注册，本地调用 |

**当前问题**：`ONTOLOGY_LOAD_MODE=db_query` 仅在 `datacloud-analysis/i18n/prompts.py` 中影响 LLM 提示词文本，**工具挂载逻辑未实现**。`init_agent_conf.py` 中无任何对 `ONTOLOGY_LOAD_MODE` 的读取，始终走 `ontology_query` 路径。

---

## 当前代码路径（ontology_query，现有逻辑）

```
InitDataCloudDigitalEmployeePlugin.register_agent_configs()
  └─ _handle_single_agent_detail()
       │
       ├─ _build_dynamic_tools_with_diagnostics()
       │     └─ _build_ontology_tools_with_diagnostics()
       │           └─ 遇到 OBJECT/VIEW → skip
       │                 reason: "object_view_use_generic_query_objects_tool"
       │
       ├─ 收集 mounted_objects[]（所有 OBJECT/VIEW 的 resource_code）
       ├─ _build_shared_loader() → OntologyLoader 实例
       └─ AgentConfig.extra = {
               "tool_metadata": ...,
               "mounted_objects": [...],   ← 传递给 create_agent
               "loader": shared_loader,    ← 运行时 OntologyToolLoader 使用
           }

运行时（create_agent 内部）：
  OntologyToolLoader 从 loader 动态生成 query_{code} / compute_{code} 工具
```

---

## 新增 db_query 模式路径

```
InitDataCloudDigitalEmployeePlugin.register_agent_configs()
  └─ _handle_single_agent_detail()
       │
       ├─ 读取 ONTOLOGY_LOAD_MODE
       │
       ├─ == "db_query"
       │     ├─ _build_shared_loader()       → loader（复用现有方法）
       │     ├─ _build_db_query_tools()      → {"data_query_{code}": tool, ...}
       │     │     └─ 每个 OBJECT/VIEW resource → _build_single_db_query_tool()
       │     ├─ mounted_objects = []         （不走 OntologyToolLoader 路径）
       │     └─ AgentConfig.extra = {
       │             "tool_metadata": ...,
       │             "mounted_objects": [],  ← 空，禁止运行时动态生成
       │             "loader": None,         ← 不传 loader
       │         }
       │
       └─ 其他 / "ontology_query"（默认）
             └─ 现有逻辑不变
```

---

## 实现规格

### 唯一改动文件

`byclaw-all/byclaw-data/src/byclaw_data/plugins/worker_plugins/init_agent_conf.py`

### 新增方法

#### 1. `_ontology_load_mode() -> str`

读取 `ONTOLOGY_LOAD_MODE` 环境变量，默认返回 `"ontology_query"`。

```python
@staticmethod
def _ontology_load_mode() -> str:
    """Read ONTOLOGY_LOAD_MODE; returns 'ontology_query' by default."""
    return os.environ.get("ONTOLOGY_LOAD_MODE", "ontology_query").strip().lower()
```

#### 2. `_build_db_query_tools(agent_id, rel_resource_list, loader) -> dict`

遍历 `relResourceList`，对 `resourceBizType` 为 `OBJECT` 或 `VIEW` 的条目调用
`_build_single_db_query_tool()` 构建工具，返回 `{"data_query_{code}": tool, ...}` 字典。

- 非 OBJECT/VIEW 类型（如 AGENT/TOOL）：`logger.debug` 跳过
- `resource_code` 为空：`logger.warning` 跳过
- 单个工具构建异常：`logger.warning` 跳过，不中断其他工具

#### 3. `_build_single_db_query_tool(resource_code, resource_biz_type, resource_name, resource_desc, loader) -> StructuredTool`

工具名：`data_query_{resource_code}`（如 `data_query_Order`）

入参 Schema：

```python
class _DataQuerySchema(BaseModel):
    question: str = Field(description="自然语言查询问题")
```

调用逻辑：

```python
# OBJECT 类型
async def _tool(question: str) -> Any:
    obj = loader.get_object(resource_code)
    return await obj.query(question, include_plan=True)

# VIEW 类型
async def _tool(question: str) -> Any:
    view = loader.get_view(resource_code)
    return await view.query(question, include_plan=True)
```

底层均为本地调用（`datacloud-data` SDK 的 `Object.query()` / `View.query()`），不经过 MCP。

### `_handle_single_agent_detail` 改造位置

在现有方法内，**`mounted_objects` 收集段**替换为如下模式分支：

```python
load_mode = self._ontology_load_mode()

if load_mode == "db_query":
    # db_query 模式：为每个 OBJECT/VIEW 静态挂载 data_query_{code} 工具
    db_loader = self._build_shared_loader(rel_resource_list)
    if db_loader is None:
        logger.warning(
            "[InitPlugin] db_query mode: loader unavailable, "
            "agent_id=%s will have no data_query tools", agent_id
        )
        db_query_tools: dict[str, Any] = {}
    else:
        db_query_tools = self._build_db_query_tools(
            agent_id=agent_id,
            rel_resource_list=rel_resource_list,
            loader=db_loader,
        )
    # 合并：dynamic_tools（AGENT 委托工具等）+ db_query_tools
    dynamic_tools = {**dynamic_tools, **db_query_tools}
    mounted_objects = []   # db_query 不使用 OntologyToolLoader
    shared_loader = None
else:
    # ontology_query 模式（默认）：现有逻辑不变
    mounted_objects = [
        snapshot["resourceCode"]
        for rel in rel_resource_list
        for snapshot in [self._rel_resource_snapshot(rel)]
        if snapshot["resourceBizType"] in {"OBJECT", "VIEW"} and snapshot["resourceCode"]
    ]
    shared_loader = (
        self._build_shared_loader(rel_resource_list)
        if mounted_objects and OntologyLoader and LangGraphPlanGenerator and TermLoader
        else None
    )
```

---

## 工具对比

| 维度 | `ontology_query`（现有） | `db_query`（新增） |
|------|------------------------|------------------|
| 工具名格式 | `query_{code}` / `compute_{code}` | `data_query_{code}` |
| 每对象工具数 | 2（query + compute） | 1 |
| 挂载时机 | 运行时（OntologyToolLoader 动态） | 启动时（静态） |
| `mounted_objects` | 有值 | 空列表 |
| `loader` in extra | 传给 create_agent | `None` |
| 底层调用 | `obj.query()` / `view.query()` | `obj.query()` / `view.query()`（相同） |
| 是否走 MCP | 否（本地） | 否（本地） |

---

## 提示词侧（已实现，无需修改）

`datacloud-analysis/i18n/prompts.py` 中已根据 `ONTOLOGY_LOAD_MODE` 注入对应提示段：

```python
if mode == "ontology_query":
    # 提示 LLM：工具名格式为 query_{code} / compute_{code}
if mode == "db_query":
    # 提示 LLM：工具名格式为 data_query_{code}
```

工具挂载实现后，提示词与实际挂载的工具名将完全对齐，无需额外修改。

---

## 错误处理策略

| 场景 | 处理方式 |
|------|---------|
| `db_query` 模式下 `_build_shared_loader()` 返回 `None` | `logger.warning` + `db_query_tools = {}`，不中断启动 |
| 单个工具构建失败（`get_object` / `get_view` 抛异常） | `logger.warning` + 跳过该工具，继续处理其余资源 |
| `resource_code` 为空 | `logger.warning` + 跳过 |
| `resource_biz_type` 不是 OBJECT/VIEW | `logger.debug` + 跳过（正常情况：AGENT/TOOL 类型） |
| 所有工具均构建失败且无 AGENT 委托工具 | 进入现有 `empty_tool_agent_ids` 逻辑，启动失败 |

---

## 实施步骤

1. 在 `init_agent_conf.py` 中新增 `_ontology_load_mode()` 静态方法
2. 新增 `_build_db_query_tools()` 方法
3. 新增 `_build_single_db_query_tool()` 方法
4. 修改 `_handle_single_agent_detail()` 中 `mounted_objects` 收集段，插入模式分支
5. 验证 `db_query` 模式：工具名为 `data_query_{code}`，`mounted_objects` 为空，`loader` 为 `None`
6. 验证 `ontology_query` 模式（或不设置）：现有行为完全不变
