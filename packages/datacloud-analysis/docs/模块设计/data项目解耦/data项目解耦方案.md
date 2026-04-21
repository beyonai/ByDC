# byclaw-data 解耦方案

## 1. 架构原则

### 1.1 依赖规则

| 项目 | 可引用 | 不可引用 |
|---|---|---|
| `byclaw-data`（agent 侧） | `datacloud-analysis`、`by-framework-python` | `datacloud-data`、`datacloud-knowledge` |
| `byclaw-data`（mcp 侧） | `datacloud-data`、`by-framework-python` | `datacloud-knowledge` |
| `datacloud-analysis` | `datacloud-data`、`datacloud-knowledge`、`by-framework-python` | — |
| `datacloud-data` | `datacloud-knowledge`、`by-framework-python` | `datacloud-analysis` |
| `datacloud-knowledge` | `by-framework-python` | 其余三个 |

> **关键约束**：无论 agent 侧还是 mcp 侧，`byclaw-data` 均**不能直接引用 `datacloud-knowledge`**。

### 1.2 依赖关系图

```
                    ┌─────────────────────────────────────┐
                    │           by-framework-python        │
                    │      （所有项目均可引用）              │
                    └──────────────────┬──────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
┌─────────▼──────────────────────────────────────────────────────────┐
│                       byclaw-data (System 3)                        │
│                                                                     │
│   ┌─────────────────────┐       ┌──────────────────────────┐       │
│   │    agent 侧          │       │      mcp 侧               │       │
│   │  worker.py          │       │  mcp/routes.py            │       │
│   │  init_agent_conf.py │       │  mcp/result_file_storage  │       │
│   │  ~~paradigm/~~  🗑️  │       │                           │       │
│   └──────────┬──────────┘       └────────────┬─────────────┘       │
└──────────────┼──────────────────────────────┼─────────────────────┘
               │ 只允许                         │ 只允许
               ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────────────┐
│   datacloud-analysis     │    │         datacloud-data            │
│   (System 2)             │    │  (datacloud_data_sdk /            │
│   agent / tools /        │    │   datacloud_data_service)         │
│   paradigm 门面           │    │                                  │
└──────────┬───────────────┘    └────────────────┬─────────────────┘
           │ 可引用               可引用 ↗          │ 只允许
           └──────────────┐    ┌──────────────────┘
                          ▼    ▼
              ┌────────────────────────────┐
              │      datacloud-knowledge   │
              │    （知识图谱 / 意图召回）   │
              └────────────────────────────┘
```

### 1.3 边界说明

- **agent 侧**（`worker.py`、`plugins/`、`commands/`）：所有 datacloud 能力通过 `datacloud-analysis` 门面访问，不感知 `datacloud-data` 和 `datacloud-knowledge` 的内部实现。
- **mcp 侧**（`mcp/`）：byclaw-data 作为 MCP 适配层，需直接驱动 `datacloud_data_service` 启动 MCP 服务，允许引用 `datacloud-data`，但**不允许**引用 `datacloud-knowledge`。
- **`paradigm/` 目录**：**已废弃，待删除**。该目录的查询澄清范式逻辑已迁移或将迁移至 `datacloud-analysis`，不作为解耦迁移目标，直接删除即可消除 V-7 ～ V-10 全部违规。

---

## 2. 现状违规全量扫描

扫描范围：`byclaw-data/src/byclaw_data/`

### 2.1 违规清单（按新规则评定）

| # | 文件 | 引用包 | 导入内容 | 新规则下状态 | 所在侧 | 处置方式 |
|---|---|---|---|---|---|---|
| V-1 | `plugins/worker_plugins/init_agent_conf.py` | `datacloud_data_sdk` | `OntologyLoader` / `TermLoader` / `LangGraphPlanGenerator`（守卫 + `configure` 构造） | ❌ **违规** | agent 侧 | 迁移至 `datacloud-analysis` |
| V-2 | `plugins/worker_plugins/init_agent_conf.py` | `datacloud_data_sdk` | `_build_single_db_query_tool` 内 `loader.get_view/get_object().query()` | ❌ **违规** | agent 侧 | 迁移至 `datacloud-analysis` |
| V-3 | `mcp/routes.py` | `datacloud_data_sdk` | `OntologyLoader` / `TermLoader` | ✅ **允许** | mcp 侧 | 保留 |
| V-4 | `mcp/routes.py` | `datacloud_data_service` | `get_settings` / `create_app as create_datacloud_app` | ✅ **允许** | mcp 侧 | 保留 |
| V-5 | `mcp/result_file_storage.py` | `datacloud_data_sdk` | `ResultFileStorage` / `normalize_logical_file_path` / `get_current_context` | ✅ **允许** | mcp 侧 | 保留 |
| V-6 | `mcp/result_file_storage.py` | `datacloud_data_service` | `datacloud_data_service.file_storage` | ✅ **允许** | mcp 侧 | 保留 |
| V-7 | `paradigm/builder.py` | `datacloud_data_sdk` | `get_current_context` | ❌ **违规** | agent 侧 | 🗑️ **随 `paradigm/` 目录删除** |
| V-8 | `paradigm/builder.py` | `datacloud_knowledge` | `TermType` / `get_session` | ❌ **违规** | agent 侧 | 🗑️ **随 `paradigm/` 目录删除** |
| V-9 | `paradigm/builder.py` | `datacloud_knowledge` | `typed_multi_recall_with_session` / `search_all_candidates_with_name_id` | ❌ **违规** | agent 侧 | 🗑️ **随 `paradigm/` 目录删除** |
| V-10 | `paradigm/query_clarification_stream.py` | `datacloud_knowledge` | `analyze_query_clarification` / `ClarificationResult` / `StreamEvent` / `StreamEventKind` | ❌ **违规** | agent 侧 | 🗑️ **随 `paradigm/` 目录删除** |

**汇总**：
- 4 处（V-3 ～ V-6）mcp 侧，新规则下合规，保留
- 4 处（V-7 ～ V-10）随 `paradigm/` 目录删除自动消除
- **2 处需主动迁移**（V-1、V-2）

---

### 2.2 待处理违规分析

#### A 组：`init_agent_conf.py`（V-1 / V-2）——agent 侧直接引用 SDK

| 违规 | 现状代码 | 解耦方案 |
|---|---|---|
| V-1 守卫导入 + `loader.configure(LangGraphPlanGenerator, TermLoader, ...)` | `byclaw-data` 直接构造 `datacloud_data_sdk` 对象传入 `configure()` | `datacloud-analysis` 提供 `configure_loader(loader, *, model, base_url, api_key, csv_base_dir, ...)` 包装函数 |
| V-2 `_build_single_db_query_tool` 直调 SDK 查询链 | `loader.get_view/get_object().query()` 写在 System 3，无单测保障 | `OntologyToolLoader.build_nl_query_tool(resource_code, resource_biz_type, ...)` 迁移到 System 2 |

---

## 3. 解耦路径

```
阶段一（已完成）
  ✅ OWL 加载 + inject_virtual_actions → OntologyToolLoader._build_loader()

阶段二（当前，P0 / P1）
  → V-2：OntologyToolLoader.build_nl_query_tool() 迁入 System 2
  → V-1：datacloud_analysis.tools.ontology_tool_loader.configure_loader() 封装
  → 🗑️ paradigm/ 目录删除（V-7 ～ V-10 自动消除）

验收标准（阶段二完成后）
  grep -r "datacloud_knowledge\|datacloud_data_sdk\|datacloud_data_service" \
    byclaw-data/src/byclaw_data/ \
    --include="*.py" \
    | grep -v "byclaw_data/mcp/"
  → 结果为空
```

---

## 4. datacloud-analysis 需要新增的出口 API（阶段二）

| 新增内容 | 类型 | 解决违规 | 难度 |
|---|---|---|---|
| `OntologyToolLoader.build_nl_query_tool(resource_code, resource_biz_type, resource_name, resource_desc, *, inject_context_knowledge=True)` | 实例方法 | V-2 | 低 |
| `datacloud_analysis.tools.ontology_tool_loader.configure_loader(loader, *, model, base_url, api_key, csv_base_dir, sql_execution_mode, ...)` | 模块级函数 | V-1 | 低 |

---

## 5. 废弃文件清单

### `byclaw-data/src/byclaw_data/paradigm/`（待删除）

> 该目录包含旧版查询澄清范式实现，已被 `datacloud-analysis` 的对应能力取代。删除后 V-7 ～ V-10 四处违规自动消除。

删除前需确认以下引用已清理或不再使用：

| 文件 | 被谁引用 | 确认状态 |
|---|---|---|
| `paradigm/builder.py` | — | 待确认 |
| `paradigm/query_clarification_stream.py` | — | 待确认 |

---

## 6. 附录：各违规点代码现状

### init_agent_conf.py（agent 侧，V-1 / V-2，需迁移）

```python
# V-1：顶部守卫导入
try:
    from datacloud_data_sdk.ontology.loader import OntologyLoader        # ← 违规
    from datacloud_data_sdk.ontology.term_loader import TermLoader        # ← 违规
    from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator  # ← 违规
except ImportError:
    ...

# V-1：configure 调用直接构造 SDK 对象
loader.configure(
    plan_generator=LangGraphPlanGenerator(...),   # ← 违规
    term_loader=TermLoader.from_config({}),       # ← 违规
    ...
)

# V-2：NL 查询工具构建直调 SDK 查询链
async def _execute(query, contextKnowledge=""):
    view = loader.get_view(resource_code)             # ← 违规
    return await view.query(question=query, ...)      # ← 违规
```

### mcp/routes.py（mcp 侧，V-3 / V-4，✅ 合规保留）

```python
from datacloud_data_sdk.ontology.loader import OntologyLoader         # ✅ mcp 侧允许
from datacloud_data_service.config import get_settings                # ✅ mcp 侧允许
from datacloud_data_service.api.routes import create_app as create_datacloud_app  # ✅ mcp 侧允许
from datacloud_data_sdk.ontology.term_loader import TermLoader         # ✅ mcp 侧允许
```

### mcp/result_file_storage.py（mcp 侧，V-5 / V-6，✅ 合规保留）

```python
from datacloud_data_sdk.file_storage.base import ResultFileStorage     # ✅ mcp 侧允许
from datacloud_data_sdk.file_storage.scoped_paths import normalize_logical_file_path  # ✅ mcp 侧允许
from datacloud_data_sdk.context import get_current_context             # ✅ mcp 侧允许
import datacloud_data_service.file_storage as file_storage_module     # ✅ mcp 侧允许
```

### paradigm/（🗑️ 废弃，待删除，V-7 ～ V-10 随之消除）

```python
# paradigm/builder.py
from datacloud_data_sdk.context import get_current_context             # ← V-7，随目录删除
from datacloud_knowledge.knowledge_search.db.models import TermType    # ← V-8，随目录删除
from datacloud_knowledge.knowledge_search.db.connection import get_session  # ← V-8，随目录删除
from datacloud_knowledge.intent import typed_multi_recall_with_session # ← V-9，随目录删除
from datacloud_knowledge.intent import search_all_candidates_with_name_id  # ← V-9，随目录删除

# paradigm/query_clarification_stream.py
from datacloud_knowledge.intent import analyze_query_clarification     # ← V-10，随目录删除
from datacloud_knowledge.intent.types import ClarificationResult, StreamEvent, StreamEventKind  # ← V-10，随目录删除
```
