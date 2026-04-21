## 5. 耦合现状审查（2026-04）

> 本节对 `init_agent_conf.py`（System 3）与 `datacloud-analysis`（System 2）、`datacloud-data`（`datacloud_data_sdk`）的耦合情况做全量扫描，记录现状与待办。

### 5.1 扫描对象

```
byclaw-data/src/byclaw_data/plugins/worker_plugins/init_agent_conf.py
```

### 5.2 耦合清单

| #    | 耦合位置（方法）                         | 耦合包               | 耦合内容                                                     | 当前状态                 | 性质                                                   |
| ---- | ---------------------------------------- | -------------------- | ------------------------------------------------------------ | ------------------------ | ------------------------------------------------------ |
| C-1  | 顶部 try-import（L34-40）                | `datacloud_data_sdk` | `OntologyLoader` / `TermLoader` / `LangGraphPlanGenerator` 仅用于可用性守卫 `if OntologyLoader and ...` | 存在，可接受             | 可用性守卫；SDK 不存在时优雅降级                       |
| C-2  | `_build_shared_loader`                   | `datacloud_analysis` | `OntologyToolLoader._build_loader(Path(scene_path))`         | ✅ **已解耦**（本轮迁移） | System 3 → System 2，合理单向消费                      |
| C-3  | `_build_shared_loader`                   | `datacloud_data_sdk` | `loader.configure(plan_generator=LangGraphPlanGenerator(...), term_loader=TermLoader.from_config({}), ...)` | ❌ **仍耦合**             | System 3 直接构造 SDK 对象并调用 SDK `configure()` API |
| C-4  | `_build_single_db_query_tool`            | `datacloud_data_sdk` | `loader.get_view(code)` → `view.query(...)` / `loader.get_object(code)` → `obj.query(...)` | ❌ **仍耦合**             | System 3 持有 SDK 自然语言查询调用链                   |
| C-5  | `_build_delegate_tools_with_diagnostics` | `datacloud_analysis` | `from datacloud_analysis.tools.delegate import build_delegate_tool` | 存在，合理               | System 3 消费 System 2 工具工厂；合理单向依赖          |
| C-6  | `AgentConfig.extra["loader"]`            | `datacloud_data_sdk` | `shared_loader`（OntologyLoader 实例）以 `Any` 类型经 `extra` 字段传递给 `create_agent` | 存在，待观察             | duck typing 传递；下游感知 loader 接口细节             |

---

### 5.3 已解耦项说明（C-2）

迁移前 `_build_shared_loader` 直接调用：

```python
loader = OntologyLoader()
loader.load_from_owl_directory(scene_path)
inject_virtual_actions(loader)        # System 3 必须知道这个细节
```

迁移后：

```python
from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader as _OntologyToolLoader
loader = _OntologyToolLoader._build_loader(Path(scene_path))   # 委托给 System 2
```

OWL 加载与虚拟动作注入完全内聚到 System 2，System 3 不再感知 `OntologyLoader`、`inject_virtual_actions` 的存在。

---

### 5.4 待解耦项分析

#### C-3：`loader.configure()` 仍耦合 `datacloud_data_sdk`

**现状**：

```python
loader.configure(
    plan_generator=LangGraphPlanGenerator(model=..., base_url=..., api_key=..., ...),
    term_loader=TermLoader.from_config({}),
    csv_base_dir=...,
    sql_execution_mode="internal",
)
```

System 3 直接构造 `LangGraphPlanGenerator`（SDK 对象）和 `TermLoader`（SDK 对象）并调用 SDK 的 `configure()` 方法。若 `configure()` 签名或这两个类的构造参数变更，System 3 必须同步修改。

**目标**：System 3 只提供**原始配置值**（字符串 / 路径），不直接构造 SDK 对象。

**建议方案**：在 `OntologyToolLoader` 或独立工厂函数中封装 `configure_loader(loader, *, model, base_url, api_key, ...)` ，System 3 只调用：

```python
from datacloud_analysis.tools.ontology_tool_loader import configure_loader

configure_loader(
    loader,
    model=os.environ.get("DATACLOUD_LLM_MODEL", ...),
    base_url=os.environ.get("DATACLOUD_LLM_API_BASE"),
    api_key=os.environ.get("DATACLOUD_LLM_API_KEY"),
    csv_base_dir=...,
)
```

**优先级**：P2（`configure()` API 目前稳定，当前风险可控；SDK 升级时 System 3 是第一个断点）

---

#### C-4：`_build_single_db_query_tool` 直调 SDK 查询链

**现状**：

```python
@staticmethod
def _build_single_db_query_tool(*, resource_code, resource_biz_type, resource_name, resource_desc, loader):
    if resource_biz_type == "VIEW":
        async def _execute(query, contextKnowledge=""):
            view = loader.get_view(resource_code)           # ← SDK API
            return await view.query(question=query, ...)    # ← SDK API
    else:
        async def _execute(query, contextKnowledge=""):
            obj = loader.get_object(resource_code)          # ← SDK API
            return await obj.query(question=query, ...)     # ← SDK API
```

System 3 持有 `loader.get_view/get_object().query()` 调用链，直接绑定 SDK 自然语言查询接口。
若 `query()` 签名变更，System 3 是唯一断点，且此方法无法在不依赖真实 SDK 的情况下单测。

**目标**：将 NL 查询工具的构建逻辑迁移到 `OntologyToolLoader`（System 2）。

**建议方案**：在 `OntologyToolLoader` 新增实例方法：

```python
def build_nl_query_tool(
    self,
    resource_code: str,
    resource_biz_type: str,
    resource_name: str,
    resource_desc: str,
    *,
    inject_context_knowledge: bool = True,
) -> Any:
    """构建 data_query_{code} 自然语言查询工具（用于 redirect_tools）。"""
    ...
```

System 3 调用：

```python
tool = ontology_tool_loader.build_nl_query_tool(
    resource_code=resource_code,
    resource_biz_type=resource_biz_type,
    resource_name=snapshot["resourceName"],
    resource_desc=snapshot["resourceDesc"],
)
```

`contextKnowledge` 是 `QueryClarificationPlugin` 在 before_callback 中注入的字段，通过 `inject_context_knowledge` 参数控制是否在 schema 中包含该字段，默认 `True`（byclaw-data 场景），System 3 无需感知实现细节。

**优先级**：P1（此处无单测保障；SDK `.query()` 接口变更时 System 2 测试体系无法覆盖该断点）

---

### 5.5 分工边界目标状态（含 C-3 / C-4 解耦后）

| 职责                                      | System 2（`datacloud-analysis`）  | System 3（`byclaw-data`） |
| ----------------------------------------- | --------------------------------- | ------------------------- |
| OWL 加载 + inject_virtual_actions         | ✅ 已内聚                          | ❌ 不感知                  |
| NL 查询工具构建（`data_query_*`）         | ✅ **待迁移**（C-4，P1）           | ❌ 不感知                  |
| loader runtime 配置包装                   | ✅ **待提供**（C-3，P2）           | 只传入原始字符串值        |
| 挂载对象 / ontology_path                  | 接收                              | ✅ 业务配置                |
| LLM 模型 / API Key / workspace            | 不涉及                            | ✅ 业务配置（运行时环境）  |
| StructuredTool 产出（query/compute 族）   | ✅ 已实现                          | 消费方                    |
| StructuredTool 产出（redirect NL 查询族） | ✅ **待实现**（C-4）               | 消费方                    |
| Agent delegate 工具                       | ✅ 已实现（`build_delegate_tool`） | 消费方                    |

