# LangGraph 重构方案

> 版本：v1.0  
> 日期：2026-04-10  
> 状态：设计中

---

## 1. 背景与目标

### 1.1 背景

当前存在两个并行的 analysis 模块：

| 模块 | 路径 | 状态 |
|------|------|------|
| `datacloud-analysis` | `packages/datacloud-analysis` | 主用模块，基于 3-node LangGraph |
| `datacloud-analysis-bak` | `packages/datacloud-analysis-bak` | 旧版备份，待废弃 |

调用入口来自 `byclaw-data` 的两个文件：
- `byclaw-all/byclaw-data/src/byclaw_data/main.py` — 启动入口，加载环境变量，调用 `run_worker(DataCloudWorker, plugins=[...])`
- `byclaw-all/byclaw-data/src/byclaw_data/worker.py` — 核心实现，继承 `GatewayWorker`，调用 `create_agent()`

### 1.2 核心问题

**问题1：接口不匹配**  
`worker.py:_build_graph()` 调用 `create_agent(mounted_objects=mounted_objects, ...)`，但现有 `agent.py:create_agent()` 签名中**不接受** `mounted_objects` 参数，导致运行时 TypeError。

**问题2：工具挂载逻辑缺失**  
Agent 初始化时应根据 OWL 文件中的本体定义，自动为每个挂载的对象/视图生成：
- `query_{对象编码}` — 查询工具
- `compute_{本体编码}` — 聚合计算工具
- 本体下定义的其它动作工具

目前该逻辑在 `datacloud-analysis-bak` 中有部分实现，但已与主模块脱离。

**问题3：旧模块冗余**  
`datacloud-analysis-bak` 中包含大量过时实现（旧中间件、OWL parser、依赖注入等），需要将有价值的逻辑迁移并彻底废弃该模块。

### 1.3 目标

1. 废弃 `datacloud-analysis-bak` 模块
2. 修复 `create_agent()` 与 `worker.py` 的接口不匹配
3. 在 `datacloud-analysis` 中实现基于 OWL/本体定义的动态工具挂载
4. 工具命名遵循 `query_{code}` / `compute_{code}` 约定
5. 修正 `by-framework-python` 引用的类名

---

## 2. 现状分析

### 2.1 调用链全景

```
main.py
  └─ run_worker(DataCloudWorker, plugins=[
       InitDataCloudDigitalEmployeePlugin,   # 从 AI Factory 加载 agent 配置
       ...
     ])
       │
       └─ DataCloudWorker (继承 GatewayWorker)
            │
            ├─ start_heartbeat()
            │    └─ bootstrap.setup()        # 初始化 checkpointer、DB 表
            │
            └─ process_command(command, context)
                 │
                 ├─ 从 AgentConfig 提取参数：
                 │    ├─ tools_dict          # dict[str, Callable] — 预构建的动态工具
                 │    ├─ prompts_dict        # dict[str, str]
                 │    └─ mounted_objects     # list[str] — OBJ/VIEW 编码列表
                 │
                 ├─ _build_graph(
                 │    tools_dict=...,
                 │    prompts_dict=...,
                 │    mounted_objects=...    # ← 当前传入但 create_agent 不接受
                 │  )
                 │    └─ create_agent(...)   # ← 接口不匹配，运行时报错
                 │
                 └─ _stream_graph(target_graph, graph_input, config)
                      └─ target_graph.astream_events(...)
```

### 2.2 `InitDataCloudDigitalEmployeePlugin` 如何构建 `mounted_objects`

```python
# init_agent_conf.py 第 214-221 行
mounted_objects = []
for rel in rel_resource_list:
    snapshot = self._rel_resource_snapshot(rel)
    resource_biz_type = snapshot["resourceBizType"]
    resource_code = snapshot["resourceCode"]
    if resource_biz_type in {"OBJECT", "VIEW"} and resource_code:
        mounted_objects.append(resource_code)
```

`mounted_objects` 是一个字符串列表，每个元素是 OBJECT 或 VIEW 类型资源的编码（如 `"Order"`, `"CustomerView"` 等）。

### 2.3 `datacloud-data-service` 中的工具生成器（现有实现）

工具生成逻辑已在 `datacloud-data-service` 中实现，可直接复用：

| 类/函数 | 路径 | 功能 |
|--------|------|------|
| `DynamicQueryToolGenerator` | `datacloud_data_service/tools/dynamic_query_tool_generator.py` | 为 DB/KB 对象生成 `query_{code}` 工具 |
| `ActionToolGenerator` | `datacloud_data_service/tools/action_tool_generator.py` | 为 `OntologyAction` 生成动作工具 |
| `build_query_schema()` | `datacloud_data_sdk/virtual_action/generator.py` | 生成查询字段 schema（含过滤、排序、分页） |
| `build_compute_schema()` | `datacloud_data_sdk/virtual_action/generator.py` | 生成聚合计算 schema（含分组、指标、having） |

生成的工具命名规则：
```python
# 查询工具
tool_name = f"query_{object_code}"       # 例：query_Order, query_CustomerView

# 计算/聚合工具
tool_name = f"compute_{ontology_code}"   # 例：compute_SalesOntology

# 动作工具（本体下定义的其它工具）
tool_name = f"{object_code}_{action_name}"  # 例：Order_create, Order_update
```

### 2.4 `datacloud-analysis-bak` 中的旧实现（参考用，将废弃）

| 文件 | 功能 | 是否迁移 |
|------|------|---------|
| `tools/owl_parser.py` | OWL XML 正则解析（简化实现） | 否，改用 `datacloud-data-sdk` |
| `tools/ontology_loader.py` | 三种加载模式：MCP/动态/统一接口 | 简化后迁移工具注册逻辑 |
| `tools/oql/query_objects.py` | 通用查询工具 | 否，由 `query_{code}` 替代 |
| `tools/oql/execute_action.py` | 通用动作工具 | 否，由动作工具替代 |
| `middlewares/knowledge_injection.py` | 本体 Schema 注入到 system message | 迁移为 tool_hook_plugin |
| `dependencies.py` | 旧式全局依赖注入 | 否，改用环境变量+SDK |

---

## 3. 重构架构设计

### 3.1 整体架构（重构后）

```
byclaw-data worker.py
│
├─ _build_graph(tools_dict, prompts_dict, mounted_objects)
│
└─ create_agent(
     model, api_key, base_url,
     tools=tools_dict,
     mounted_objects=mounted_objects,   # ← 新增参数
     prompts_overwrite=prompts_dict,
   )
     │
     ├─ [步骤1] 加载本体元数据
     │   └─ OntologyToolLoader.load(mounted_objects)
     │        ├─ 调用 datacloud_data_sdk.OntologyLoader
     │        ├─ 为每个 Object/View 生成 query_{code} 工具
     │        ├─ 为支持计算的本体生成 compute_{code} 工具
     │        └─ 为本体下的 Action 生成动作工具
     │
     ├─ [步骤2] 合并工具
     │   └─ merged_tools = ontology_tools | (tools or {})
     │        # tools_dict 中的同名工具优先（caller 可覆盖）
     │
     ├─ [步骤3] 构建图
     │   └─ build_analysis_graph(
     │        prompts_overwrite=prompts_overwrite,
     │        tools=merged_tools,       # 工具在闭包中注入
     │      )
     │
     └─ [步骤4] 编译图（含 checkpointer）
          └─ graph.compile(checkpointer=get_checkpointer())
```

### 3.2 工具挂载流程

```
mounted_objects = ["Order", "CustomerView", "SalesOntology"]
         │
         ▼
OntologyToolLoader.load(mounted_objects)
         │
         ├─ Order (OBJECT, DB类型)
         │    ├─ query_Order      ← DynamicQueryToolGenerator 生成
         │    ├─ compute_Order    ← build_compute_schema 生成（若有可聚合字段）
         │    ├─ Order_create     ← ActionToolGenerator 生成
         │    └─ Order_update     ← ActionToolGenerator 生成
         │
         ├─ CustomerView (VIEW)
         │    └─ query_CustomerView  ← DynamicQueryToolGenerator 生成
         │
         └─ SalesOntology (ONTOLOGY)
              └─ compute_SalesOntology ← build_compute_schema 生成
```

### 3.3 LangGraph 3-node 架构（保持不变）

```
START
  │
  ▼
intend_node                    # 命令路由 + 意图分类
  │
  ├─[command_done]──────────▶ END
  │
  └─[react/chitchat]
         │
         ▼
execution_node                 # ReAct 循环（工具在闭包中）
         │
         ▼
respond_node                   # 格式化输出
         │
         ▼
       END
```

---

## 4. 详细设计

### 4.1 新增 `OntologyToolLoader`

**路径**：`src/datacloud_analysis/tools/ontology_tool_loader.py`

```python
"""
从本体定义动态生成 query_{code} / compute_{code} / action 工具。
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


class OntologyToolLoader:
    """
    根据 mounted_objects 列表，从 datacloud_data_sdk 加载本体元数据，
    生成对应的 LangChain 工具字典。

    生成规则：
    - query_{code}   : 每个 OBJECT/VIEW 生成一个查询工具
    - compute_{code} : 每个有可聚合字段的 OBJECT/ONTOLOGY 生成一个计算工具
    - {code}_{action}: 本体下定义的每个动作生成一个工具
    """

    def __init__(self, mounted_objects: list[str] | None = None):
        self._mounted_objects = mounted_objects or []

    def load(self) -> dict[str, Any]:
        """
        加载所有挂载对象的工具。

        Returns:
            dict[str, Callable]: key 为工具名，value 为可调用的工具对象
        """
        if not self._mounted_objects:
            return {}

        tools: dict[str, Any] = {}

        try:
            # 通过 datacloud_data_sdk 加载本体定义
            from datacloud_data_sdk import OntologyLoader  # noqa: PLC0415
            ontology_loader = OntologyLoader()

            for obj_code in self._mounted_objects:
                obj_def = ontology_loader.get(obj_code)
                if obj_def is None:
                    logger.warning("OntologyToolLoader: 未找到本体定义 code=%s，跳过", obj_code)
                    continue

                # 生成 query_{code} 工具
                query_tool = self._make_query_tool(obj_code, obj_def)
                if query_tool is not None:
                    tools[f"query_{obj_code}"] = query_tool

                # 生成 compute_{code} 工具（仅对有聚合字段的本体）
                compute_tool = self._make_compute_tool(obj_code, obj_def)
                if compute_tool is not None:
                    tools[f"compute_{obj_code}"] = compute_tool

                # 生成动作工具
                action_tools = self._make_action_tools(obj_code, obj_def)
                tools.update(action_tools)

        except ImportError:
            logger.warning(
                "OntologyToolLoader: datacloud_data_sdk 未安装，"
                "跳过本体工具加载（mounted_objects=%s）",
                self._mounted_objects,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("OntologyToolLoader: 加载本体工具失败: %s", exc, exc_info=True)

        logger.info(
            "OntologyToolLoader: 已加载工具 count=%d keys=%s",
            len(tools),
            sorted(tools.keys()),
        )
        return tools

    def _make_query_tool(self, obj_code: str, obj_def: Any) -> Any | None:
        """为 OBJECT/VIEW 生成 query_{code} 工具。"""
        try:
            from datacloud_data_service.tools.dynamic_query_tool_generator import (  # noqa: PLC0415
                DynamicQueryToolGenerator,
            )
            return DynamicQueryToolGenerator(obj_def).generate()
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成 query_%s 工具失败: %s", obj_code, exc)
            return None

    def _make_compute_tool(self, obj_code: str, obj_def: Any) -> Any | None:
        """为有可聚合字段的本体生成 compute_{code} 工具。"""
        try:
            from datacloud_data_sdk.virtual_action.generator import build_compute_schema  # noqa: PLC0415
            schema = build_compute_schema(obj_def)
            if not schema:
                return None
            # 封装为 LangChain StructuredTool
            from langchain_core.tools import StructuredTool  # noqa: PLC0415
            return StructuredTool(
                name=f"compute_{obj_code}",
                description=f"对 {obj_code} 进行聚合计算（分组统计、指标汇总等）",
                args_schema=schema,
                coroutine=obj_def.compute_async,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("compute_%s 工具不适用或生成失败: %s", obj_code, exc)
            return None

    def _make_action_tools(self, obj_code: str, obj_def: Any) -> dict[str, Any]:
        """为本体下定义的每个动作生成工具。"""
        result: dict[str, Any] = {}
        try:
            from datacloud_data_service.tools.action_tool_generator import (  # noqa: PLC0415
                ActionToolGenerator,
            )
            action_tools = ActionToolGenerator(obj_def).generate_tools()
            for tool in action_tools:
                result[tool.name] = tool
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成 %s 动作工具失败: %s", obj_code, exc)
        return result
```

### 4.2 修改 `create_agent()` 签名

**路径**：`src/datacloud_analysis/agent.py`

```python
def create_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str | None = None,
    system_prompt: str | None = None,
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    mounted_objects: list[str] | None = None,   # ← 新增
) -> Any:
    """
    Create a deep agent for DataCloud.

    Args:
        mounted_objects: OBJECT/VIEW/ONTOLOGY 编码列表。
            若提供，则自动从 datacloud_data_sdk 加载本体定义，
            并为每个对象生成 query_{code} / compute_{code} / action 工具，
            与 tools 参数合并（tools 参数中同名工具优先）。
    """
    ...
    # 步骤1: 加载本体工具
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    ontology_tools = OntologyToolLoader(mounted_objects).load()

    # 步骤2: 合并工具（caller 传入的 tools 优先级更高）
    merged_tools = {**ontology_tools, **(tools or {})}

    logger.info(
        "create_agent: ontology_tools=%d extra_tools=%d merged=%d mounted_objects=%s",
        len(ontology_tools),
        len(tools or {}),
        len(merged_tools),
        mounted_objects,
    )

    # 步骤3: 构建图（merged_tools 替代原来的 tools）
    graph = build_analysis_graph(
        prompts_overwrite=prompts_overwrite,
        tools=merged_tools,
    )
    ...
```

### 4.3 `execution/node.py` — 无需修改

`execution_node` 通过闭包接收 `default_tools`，工具合并在 `create_agent()` 层完成，`node.py` 不需要感知 `mounted_objects` 的存在，保持现有的 `_build_tools_list()` 逻辑即可。

### 4.4 `graph_builder.py` — 无需修改

`build_analysis_graph(tools=merged_tools, ...)` 的签名已经接受 `tools` 参数，无需变更。

---

## 5. `by-framework-python` 类名核查

经过搜索，`by-framework-python` 框架（`by_framework` 包）与 `datacloud_analysis` 完全解耦，框架内部**没有**任何对 `datacloud_analysis`、OQL、ontology 的直接引用。

`byclaw-data/worker.py` 引用的框架类如下，均已确认与框架当前导出一致：

| 引用类/函数 | 框架路径 | 状态 |
|-----------|---------|------|
| `GatewayWorker` | `by_framework.worker.worker.GatewayWorker` | ✓ 一致 |
| `AgentContext` | `by_framework.worker.context.AgentContext` | ✓ 一致 |
| `AgentConfig` | `by_framework.core.extensions.agent_config.AgentConfig` | ✓ 一致 |
| `run_worker` | `by_framework.worker.app.run_worker` | ✓ 一致 |
| `Plugin` | `by_framework.core.extensions.plugin.Plugin` | ✓ 一致 |
| `PluginRegistry` | `by_framework.core.extensions.registry.PluginRegistry` | ✓ 一致 |

**结论：`by-framework-python` 中无需修改任何类名。**

---

## 6. 实现步骤

### 步骤 1：新增 `OntologyToolLoader`

创建 `src/datacloud_analysis/tools/ontology_tool_loader.py`，参考 §4.1。

**验证**：

```python
from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
loader = OntologyToolLoader(["Order", "CustomerView"])
tools = loader.load()
assert "query_Order" in tools
assert "query_CustomerView" in tools
```

### 步骤 2：修改 `create_agent()` 签名

修改 `src/datacloud_analysis/agent.py`：
- 新增 `mounted_objects: list[str] | None = None` 参数
- 在构建图之前调用 `OntologyToolLoader(mounted_objects).load()`
- 合并 `ontology_tools` 与 `tools` 参数

### 步骤 3：验证 worker.py 调用链

确认 `worker.py:_build_graph()` 传入的参数：
```python
create_agent(
    model=self.model_name,
    api_key=self.api_key,
    base_url=self.base_url,
    prompts_overwrite=prompts_dict,
    tools=tools_dict,
    mounted_objects=mounted_objects,   # ← 现在可以正常接收
)
```

### 步骤 4：集成测试

| 测试场景 | 验证点 |
|---------|------|
| `mounted_objects=[]` | 无本体工具注入，行为与之前一致 |
| `mounted_objects=["Order"]` | `query_Order` 工具出现在 agent 工具列表中 |
| `mounted_objects=["Order"]` + `tools={"query_Order": custom_fn}` | `custom_fn` 覆盖自动生成的 `query_Order` |
| `datacloud_data_sdk` 未安装 | 优雅降级，记录 warning，不报错 |
| 本体无可聚合字段 | `compute_{code}` 工具不生成，不报错 |

---

## 7. 关键数据结构不变

以下结构在重构中**保持不变**：

- `AgentState` — 无字段变更
- `PlanTask` / `TaskResult` / `ArtifactRef` — 无变更
- `build_analysis_graph()` 签名 — 无变更
- `execution_node()` / `intend_node()` / `respond_node()` — 无变更
- `tool_hook_plugins/` 钩子系统 — 无变更
- `command_plugins/` 命令系统 — 无变更

---

## 8. 风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| `datacloud_data_sdk` 接口未稳定 | `OntologyToolLoader` 内所有 import 加 `try/except`，失败时降级为空工具集 |
| `mounted_objects` 中包含未知编码 | `OntologyLoader.get(code)` 返回 None 时跳过，记录 warning |
| 工具名冲突（bak vs new） | 合并规则：caller 传入的 `tools` dict 优先级高于自动生成 |
| `compute_{code}` 工具语义不清 | 工具 description 中明确说明支持的聚合操作，并在 system prompt 中补充说明 |
| 大量对象挂载导致上下文溢出 | 按需挂载（`mounted_objects` 由平台控制），`OntologyToolLoader` 不做全量加载 |
